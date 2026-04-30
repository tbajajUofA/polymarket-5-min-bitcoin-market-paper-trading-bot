"""
Public trader flow features for Polymarket BTC markets.

The goal is to summarize what public wallets are doing without trying to
identify the people behind them. The collector fetches recent trades for the
next BTC five minute market, groups them by ``proxyWallet``, checks each active
wallet's public closed-position history, and emits aggregate features.

The dashboard displays only hashed wallet identifiers. Raw wallet addresses are
used internally to query public API endpoints, but the UI intentionally avoids
profile names or personal identity guesses.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import pandas as pd
import requests


DATA_API = "https://data-api.polymarket.com"


def _safe_float(value, default=0.0):
    """Convert numeric API values while tolerating blanks and malformed data."""
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _wallet_hash(wallet):
    """Hash a public wallet address for non identifying dashboard display."""
    if not wallet:
        return None
    return hashlib.sha256(wallet.lower().encode("utf-8")).hexdigest()[:12]


def fetch_market_trades(market, limit=250):
    """Fetch public trades for one Polymarket condition id."""
    condition_id = market.get("condition_id") if market else None
    if not condition_id:
        return pd.DataFrame()

    response = requests.get(
        f"{DATA_API}/trades",
        params={"market": condition_id, "limit": limit, "takerOnly": "false"},
        timeout=20,
    )
    response.raise_for_status()
    trades = response.json()
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame(trades)


def fetch_wallet_closed_positions(wallet, limit=100):
    """Fetch public closed positions for a wallet address."""
    response = requests.get(
        f"{DATA_API}/closed-positions",
        params={"user": wallet, "limit": limit},
        timeout=20,
    )
    response.raise_for_status()
    positions = response.json()
    if not positions:
        return pd.DataFrame()
    return pd.DataFrame(positions)


def score_wallet(wallet, closed_limit=100):
    """Score a wallet from public realized PnL, win rate, and exposure."""
    positions = fetch_wallet_closed_positions(wallet, limit=closed_limit)
    if positions.empty:
        return {
            "wallet": wallet,
            "wallet_hash": _wallet_hash(wallet),
            "closed_count": 0,
            "realized_pnl": 0.0,
            "win_rate": 0.5,
            "avg_roi": 0.0,
            "score": 1.0,
        }

    realized = positions.get("realizedPnl", pd.Series(dtype=float)).map(_safe_float)
    bought = positions.get("totalBought", pd.Series(dtype=float)).map(_safe_float)
    closed_count = len(positions)
    realized_pnl = float(realized.sum())
    wins = int((realized > 0).sum())
    win_rate = wins / closed_count if closed_count else 0.5
    exposure = float(bought.abs().sum()) or 1.0
    avg_roi = realized_pnl / exposure
    score = 1.0 + max(-0.75, min(1.5, avg_roi)) + (win_rate - 0.5)

    return {
        "wallet": wallet,
        "wallet_hash": _wallet_hash(wallet),
        "closed_count": closed_count,
        "realized_pnl": realized_pnl,
        "win_rate": win_rate,
        "avg_roi": avg_roi,
        "score": max(0.1, score),
    }


def _trade_direction(row):
    """Map a trade row into UP pressure, DOWN pressure, or neutral flow."""
    outcome = str(row.get("outcome", "")).lower()
    side = str(row.get("side", "")).upper()
    if outcome == "up":
        return 1 if side == "BUY" else -1
    if outcome == "down":
        return -1 if side == "BUY" else 1
    return 0


def build_trader_signal(market, trade_limit=250, top_wallets=12, closed_limit=100):
    """Build aggregate public trader flow features for one market."""
    trades = fetch_market_trades(market, limit=trade_limit)
    collected_at = datetime.now(timezone.utc).isoformat()
    if trades.empty:
        return _empty_signal(market, collected_at)

    trades["trade_value"] = trades.apply(lambda r: _safe_float(r.get("size")) * _safe_float(r.get("price")), axis=1)
    trades["direction"] = trades.apply(_trade_direction, axis=1)
    trades["proxyWallet"] = trades["proxyWallet"].fillna("")

    wallet_flow = (
        trades.groupby("proxyWallet", dropna=True)
        .agg(
            trade_count=("proxyWallet", "size"),
            total_value=("trade_value", "sum"),
            directional_value=("trade_value", lambda s: float((s * trades.loc[s.index, "direction"]).sum())),
        )
        .reset_index()
        .sort_values("total_value", ascending=False)
    )
    wallets = wallet_flow["proxyWallet"].head(top_wallets).tolist()

    scores = []
    for wallet in wallets:
        try:
            scores.append(score_wallet(wallet, closed_limit=closed_limit))
        except requests.RequestException:
            scores.append(
                {
                    "wallet": wallet,
                    "wallet_hash": _wallet_hash(wallet),
                    "closed_count": 0,
                    "realized_pnl": 0.0,
                    "win_rate": 0.5,
                    "avg_roi": 0.0,
                    "score": 1.0,
                }
            )

    score_df = pd.DataFrame(scores)
    flow_scored = wallet_flow.merge(score_df, left_on="proxyWallet", right_on="wallet", how="left")
    flow_scored["score"] = flow_scored["score"].fillna(1.0)
    flow_scored["weighted_directional_value"] = flow_scored["directional_value"] * flow_scored["score"]

    total_value = float(trades["trade_value"].sum())
    up_value = float(trades.loc[trades["direction"] > 0, "trade_value"].sum())
    down_value = float(trades.loc[trades["direction"] < 0, "trade_value"].sum())
    smart_direction = float(flow_scored["weighted_directional_value"].sum())
    smart_abs = float((flow_scored["total_value"] * flow_scored["score"]).sum()) or 1.0
    smart_up_pressure = (smart_direction / smart_abs + 1) / 2

    signal = {
        "collected_at": collected_at,
        "timestamp": pd.to_datetime(market.get("timestamp"), unit="s", utc=True).isoformat()
        if market and market.get("timestamp")
        else None,
        "pm_slug": market.get("slug") if market else None,
        "pm_condition_id": market.get("condition_id") if market else None,
        "trader_trade_count": int(len(trades)),
        "trader_wallet_count": int(trades["proxyWallet"].nunique()),
        "trader_total_value": total_value,
        "trader_up_value": up_value,
        "trader_down_value": down_value,
        "trader_net_up_value": up_value - down_value,
        "trader_up_pressure": up_value / total_value if total_value else 0.5,
        "smart_wallet_count": int(len(score_df)),
        "smart_avg_win_rate": float(score_df["win_rate"].mean()) if not score_df.empty else 0.5,
        "smart_total_realized_pnl": float(score_df["realized_pnl"].sum()) if not score_df.empty else 0.0,
        "smart_net_up_value": smart_direction,
        "smart_up_pressure": max(0.0, min(1.0, smart_up_pressure)),
    }
    return signal, flow_scored


def _empty_signal(market, collected_at):
    """Return neutral trader features when the market has no trade data."""
    signal = {
        "collected_at": collected_at,
        "timestamp": pd.to_datetime(market.get("timestamp"), unit="s", utc=True).isoformat()
        if market and market.get("timestamp")
        else None,
        "pm_slug": market.get("slug") if market else None,
        "pm_condition_id": market.get("condition_id") if market else None,
        "trader_trade_count": 0,
        "trader_wallet_count": 0,
        "trader_total_value": 0.0,
        "trader_up_value": 0.0,
        "trader_down_value": 0.0,
        "trader_net_up_value": 0.0,
        "trader_up_pressure": 0.5,
        "smart_wallet_count": 0,
        "smart_avg_win_rate": 0.5,
        "smart_total_realized_pnl": 0.0,
        "smart_net_up_value": 0.0,
        "smart_up_pressure": 0.5,
    }
    return signal, pd.DataFrame()


def append_trader_signal(market, signals_csv="data/trader_signals.csv", leaders_csv="data/trader_leaders.csv"):
    """Append trader signal and hashed leader diagnostics to local CSV files."""
    signal, leaders = build_trader_signal(market)
    os.makedirs(os.path.dirname(signals_csv) or ".", exist_ok=True)
    pd.DataFrame([signal]).to_csv(
        signals_csv,
        mode="a",
        index=False,
        header=not os.path.exists(signals_csv),
    )

    if not leaders.empty:
        public_cols = [
            "wallet_hash",
            "trade_count",
            "total_value",
            "directional_value",
            "closed_count",
            "realized_pnl",
            "win_rate",
            "avg_roi",
            "score",
        ]
        leader_rows = leaders[[col for col in public_cols if col in leaders.columns]].copy()
        leader_rows.insert(0, "collected_at", signal["collected_at"])
        leader_rows.insert(1, "pm_slug", signal["pm_slug"])
        os.makedirs(os.path.dirname(leaders_csv) or ".", exist_ok=True)
        leader_rows.to_csv(
            leaders_csv,
            mode="a",
            index=False,
            header=not os.path.exists(leaders_csv),
        )

    return signal


def load_trader_features(signals_csv="data/trader_signals.csv"):
    """Load trader signal rows for feature joins."""
    try:
        df = pd.read_csv(signals_csv)
    except FileNotFoundError:
        return pd.DataFrame()
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    feature_cols = [
        "timestamp",
        "trader_trade_count",
        "trader_wallet_count",
        "trader_total_value",
        "trader_up_value",
        "trader_down_value",
        "trader_net_up_value",
        "trader_up_pressure",
        "smart_wallet_count",
        "smart_avg_win_rate",
        "smart_total_realized_pnl",
        "smart_net_up_value",
        "smart_up_pressure",
    ]
    return df[[col for col in feature_cols if col in df.columns]].drop_duplicates(
        subset=["timestamp"], keep="last"
    )


def merge_trader_features(raw_df, signals_csv="data/trader_signals.csv"):
    """Merge collected trader flow features into candle rows."""
    features = load_trader_features(signals_csv)
    if features.empty:
        return raw_df
    df = raw_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.merge(features, on="timestamp", how="left")


def add_trader_features_to_latest(raw_df, signal):
    """Attach live trader flow features to the latest candle row."""
    if raw_df.empty or not signal:
        return raw_df
    df = raw_df.copy()
    for key, value in signal.items():
        if key.startswith("trader_") or key.startswith("smart_"):
            df.loc[df.index[-1], key] = value
    return df
