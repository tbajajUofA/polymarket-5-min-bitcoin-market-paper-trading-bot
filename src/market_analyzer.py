"""
Polymarket trade-flow analyzer utilities.

This module is the new product core for the project. It focuses on answering:

1. Which markets are active or searchable right now?
2. Who is trading a selected market, what side are they taking, and how large?
3. Which wallets look historically strong from public closed-position data?
4. What distributions describe the current market's trade flow?

The functions are intentionally pure-ish and dataframe-oriented so they can be
called from Streamlit today, then from FastAPI workers later.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
import requests


GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO string."""
    return datetime.now(timezone.utc).isoformat()


def wallet_hash(wallet: str | None) -> str | None:
    """Return a short non-identifying wallet hash for display."""
    if not wallet:
        return None
    return hashlib.sha256(str(wallet).lower().encode("utf-8")).hexdigest()[:12]


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert API values to floats while tolerating blanks."""
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _loads_json_list(value: Any, default: list[Any] | None = None) -> list[Any]:
    """Parse Gamma JSON encoded list fields while tolerating missing values."""
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else default
    except (TypeError, json.JSONDecodeError):
        return default


def _response_items(payload: Any) -> list[dict[str, Any]]:
    """Extract list items from common Gamma API response envelopes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("events", "markets", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _market_prices(market: dict[str, Any]) -> dict[str, float]:
    """Return outcome price map from a Gamma market object."""
    outcomes = _loads_json_list(market.get("outcomes"), [])
    prices = _loads_json_list(market.get("outcomePrices"), [])
    price_map: dict[str, float] = {}
    for idx, outcome in enumerate(outcomes):
        price_map[str(outcome)] = safe_float(prices[idx] if idx < len(prices) else None)
    return price_map


def _normalize_event_market(event: dict[str, Any], market: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Normalize one Gamma event and optional market into a search result row."""
    market = market or {}
    condition_id = market.get("conditionId") or event.get("conditionId")
    if not condition_id:
        return None

    prices = _market_prices(market)
    volume = safe_float(market.get("volume", event.get("volume")))
    liquidity = safe_float(market.get("liquidity", event.get("liquidity")))
    title = event.get("title") or market.get("question") or market.get("title") or event.get("question")

    return {
        "title": title,
        "slug": event.get("slug") or market.get("slug"),
        "event_id": event.get("id"),
        "market_id": market.get("id") or event.get("id"),
        "condition_id": condition_id,
        "question": market.get("question") or title,
        "active": bool(event.get("active", market.get("active", False))),
        "closed": bool(event.get("closed", market.get("closed", False))),
        "volume": volume,
        "liquidity": liquidity,
        "end_date": market.get("endDate") or event.get("endDate") or event.get("end_date"),
        "outcomes": list(prices.keys()),
        "prices": prices,
        "url": f"https://polymarket.com/event/{event.get('slug')}" if event.get("slug") else None,
    }


def search_markets(query: str, limit: int = 25, active_only: bool = True) -> list[dict[str, Any]]:
    """
    Search Polymarket Gamma events and return normalized market candidates.

    Gamma has changed response envelopes over time, so this function accepts
    both raw lists and dict envelopes.
    """
    params = {
        "limit": limit,
        "order": "volume",
        "ascending": "false",
    }
    if query.strip():
        params["search"] = query.strip()
    if active_only:
        params["active"] = "true"
        params["closed"] = "false"

    response = requests.get(f"{GAMMA_API}/events", params=params, timeout=20)
    response.raise_for_status()
    events = _response_items(response.json())

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for event in events:
        markets = event.get("markets")
        if isinstance(markets, list) and markets:
            for market in markets:
                if not isinstance(market, dict):
                    continue
                row = _normalize_event_market(event, market)
                if row and row["condition_id"] not in seen:
                    rows.append(row)
                    seen.add(row["condition_id"])
        else:
            row = _normalize_event_market(event)
            if row and row["condition_id"] not in seen:
                rows.append(row)
                seen.add(row["condition_id"])

    return rows[:limit]


def fetch_market_trades(condition_id: str, limit: int = 500) -> pd.DataFrame:
    """Fetch recent public trades for one Polymarket condition id."""
    if not condition_id:
        return pd.DataFrame()
    response = requests.get(
        f"{DATA_API}/trades",
        params={"market": condition_id, "limit": limit, "takerOnly": "false"},
        timeout=25,
    )
    response.raise_for_status()
    rows = response.json()
    if not rows:
        return pd.DataFrame()
    return normalize_trades(pd.DataFrame(rows), condition_id=condition_id)


def normalize_trades(raw: pd.DataFrame, condition_id: str | None = None) -> pd.DataFrame:
    """Normalize raw Polymarket trade rows into analyzer columns."""
    if raw.empty:
        return raw

    df = raw.copy()
    if condition_id:
        df["condition_id"] = condition_id
    elif "conditionId" in df.columns:
        df["condition_id"] = df["conditionId"]
    elif "market" in df.columns:
        df["condition_id"] = df["market"]
    else:
        df["condition_id"] = None
    if "proxyWallet" in df.columns:
        wallet_series = df["proxyWallet"]
    elif "user" in df.columns:
        wallet_series = df["user"]
    else:
        wallet_series = pd.Series([""] * len(df), index=df.index)
    df["wallet"] = wallet_series.fillna("")
    df["wallet_hash"] = df["wallet"].map(wallet_hash)
    df["side"] = _column_or_default(df, "side", "").fillna("").astype(str).str.upper()
    df["outcome"] = _column_or_default(df, "outcome", "").fillna("").astype(str)
    df["price"] = _column_or_default(df, "price", 0).map(safe_float)
    df["size"] = _column_or_default(df, "size", 0).map(safe_float)
    df["trade_value"] = df["price"] * df["size"]

    timestamp = df.get("timestamp", df.get("createdAt"))
    if timestamp is not None:
        numeric_ts = pd.to_numeric(timestamp, errors="coerce")
        if numeric_ts.notna().any() and numeric_ts.dropna().median() > 10_000_000_000:
            df["timestamp"] = pd.to_datetime(numeric_ts, unit="ms", utc=True, errors="coerce")
        elif numeric_ts.notna().any():
            df["timestamp"] = pd.to_datetime(numeric_ts, unit="s", utc=True, errors="coerce")
        else:
            df["timestamp"] = pd.to_datetime(timestamp, utc=True, format="mixed", errors="coerce")
    else:
        df["timestamp"] = pd.NaT

    df["signed_value"] = df.apply(_signed_trade_value, axis=1)
    df["collected_at"] = utc_now_iso()
    keep = [
        "timestamp",
        "collected_at",
        "condition_id",
        "wallet",
        "wallet_hash",
        "side",
        "outcome",
        "price",
        "size",
        "trade_value",
        "signed_value",
    ]
    extra = [col for col in ("transactionHash", "id") if col in df.columns]
    return df[keep + extra].sort_values("timestamp", ascending=False).reset_index(drop=True)


def _column_or_default(df: pd.DataFrame, column: str, default: Any) -> pd.Series:
    """Return a dataframe column or a same-length default series."""
    if column in df.columns:
        return df[column]
    return pd.Series([default] * len(df), index=df.index)


def _signed_trade_value(row: pd.Series) -> float:
    """Map trade value into positive/negative outcome pressure."""
    side = str(row.get("side", "")).upper()
    outcome = str(row.get("outcome", "")).lower()
    value = safe_float(row.get("trade_value"))
    if side == "SELL":
        value *= -1
    if outcome in ("no", "down"):
        value *= -1
    return value


def summarize_trade_flow(trades: pd.DataFrame) -> dict[str, Any]:
    """Build high-level market-flow metrics from normalized trades."""
    if trades.empty:
        return {
            "trade_count": 0,
            "wallet_count": 0,
            "total_value": 0.0,
            "net_pressure": 0.0,
            "buy_value": 0.0,
            "sell_value": 0.0,
            "avg_price": None,
            "median_size": None,
            "largest_trade": None,
        }

    buy_value = float(trades.loc[trades["side"] == "BUY", "trade_value"].sum())
    sell_value = float(trades.loc[trades["side"] == "SELL", "trade_value"].sum())
    total_value = float(trades["trade_value"].sum())
    return {
        "trade_count": int(len(trades)),
        "wallet_count": int(trades["wallet_hash"].nunique()),
        "total_value": total_value,
        "net_pressure": float(trades["signed_value"].sum()),
        "buy_value": buy_value,
        "sell_value": sell_value,
        "buy_share": buy_value / total_value if total_value else 0.0,
        "avg_price": float(trades["price"].mean()) if not trades.empty else None,
        "median_size": float(trades["size"].median()) if not trades.empty else None,
        "largest_trade": float(trades["trade_value"].max()) if not trades.empty else None,
        "latest_trade": str(trades["timestamp"].max()) if "timestamp" in trades else None,
    }


def wallet_leaderboard(trades: pd.DataFrame) -> pd.DataFrame:
    """Aggregate selected-market trades by wallet."""
    if trades.empty:
        return pd.DataFrame()
    grouped = (
        trades.groupby(["wallet", "wallet_hash"], dropna=False)
        .agg(
            trades=("wallet_hash", "size"),
            total_value=("trade_value", "sum"),
            net_pressure=("signed_value", "sum"),
            avg_price=("price", "mean"),
            median_size=("size", "median"),
            first_seen=("timestamp", "min"),
            last_seen=("timestamp", "max"),
        )
        .reset_index()
        .sort_values("total_value", ascending=False)
    )
    grouped["dominant_side"] = np.where(grouped["net_pressure"] >= 0, "positive", "negative")
    return grouped


def fetch_wallet_closed_positions(wallet: str, limit: int = 100) -> pd.DataFrame:
    """Fetch public closed positions for a wallet address."""
    if not wallet:
        return pd.DataFrame()
    response = requests.get(
        f"{DATA_API}/closed-positions",
        params={"user": wallet, "limit": limit},
        timeout=25,
    )
    response.raise_for_status()
    rows = response.json()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def score_wallet(wallet: str, closed_limit: int = 100) -> dict[str, Any]:
    """Score one wallet from public closed-position history."""
    positions = fetch_wallet_closed_positions(wallet, limit=closed_limit)
    if positions.empty:
        return {
            "wallet": wallet,
            "wallet_hash": wallet_hash(wallet),
            "closed_count": 0,
            "realized_pnl": 0.0,
            "win_rate": 0.5,
            "avg_roi": 0.0,
            "copy_score": 0.0,
        }

    realized = positions.get("realizedPnl", pd.Series(dtype=float)).map(safe_float)
    bought = positions.get("totalBought", pd.Series(dtype=float)).map(safe_float)
    closed_count = int(len(positions))
    realized_pnl = float(realized.sum())
    wins = int((realized > 0).sum())
    win_rate = wins / closed_count if closed_count else 0.5
    exposure = float(bought.abs().sum()) or 1.0
    avg_roi = realized_pnl / exposure
    sample_score = min(1.0, closed_count / 50)
    copy_score = sample_score * ((win_rate - 0.5) * 2 + max(-0.5, min(1.0, avg_roi)))

    return {
        "wallet": wallet,
        "wallet_hash": wallet_hash(wallet),
        "closed_count": closed_count,
        "realized_pnl": realized_pnl,
        "win_rate": float(win_rate),
        "avg_roi": float(avg_roi),
        "copy_score": float(copy_score),
    }


def enrich_wallets_with_history(leaderboard: pd.DataFrame, top_n: int = 8, closed_limit: int = 75) -> pd.DataFrame:
    """Add closed-position performance to the top wallets in a leaderboard."""
    if leaderboard.empty:
        return leaderboard
    scores = []
    for wallet in leaderboard["wallet"].head(top_n):
        try:
            scores.append(score_wallet(wallet, closed_limit=closed_limit))
        except requests.RequestException:
            scores.append(
                {
                    "wallet": wallet,
                    "wallet_hash": wallet_hash(wallet),
                    "closed_count": 0,
                    "realized_pnl": 0.0,
                    "win_rate": 0.5,
                    "avg_roi": 0.0,
                    "copy_score": 0.0,
                }
            )
    if not scores:
        return leaderboard
    score_df = pd.DataFrame(scores)
    return leaderboard.merge(
        score_df[["wallet", "closed_count", "realized_pnl", "win_rate", "avg_roi", "copy_score"]],
        on="wallet",
        how="left",
    )


def distribution_summary(trades: pd.DataFrame) -> pd.DataFrame:
    """Return compact distribution stats for trade price, size, and value."""
    if trades.empty:
        return pd.DataFrame()
    rows = []
    for column in ("price", "size", "trade_value"):
        series = pd.to_numeric(trades[column], errors="coerce").dropna()
        if series.empty:
            continue
        rows.append(
            {
                "metric": column,
                "mean": float(series.mean()),
                "std": float(series.std(ddof=0)),
                "p10": float(series.quantile(0.10)),
                "p50": float(series.quantile(0.50)),
                "p90": float(series.quantile(0.90)),
                "max": float(series.max()),
            }
        )
    return pd.DataFrame(rows)


def shadow_signal(enriched_wallets: pd.DataFrame, summary: dict[str, Any]) -> dict[str, Any]:
    """Produce a cautious copy-trading style signal from wallet quality and flow."""
    if enriched_wallets.empty:
        return {"action": "WATCH", "confidence": "low", "reason": "No wallet flow yet"}

    scored = enriched_wallets.dropna(subset=["copy_score"]).copy()
    if scored.empty:
        return {"action": "WATCH", "confidence": "low", "reason": "No wallet history available"}

    smart = scored[scored["copy_score"] > 0].head(5)
    pressure = safe_float(summary.get("net_pressure"))
    if smart.empty:
        return {"action": "WATCH", "confidence": "low", "reason": "Top wallets have not shown positive history yet"}

    avg_score = float(smart["copy_score"].mean())
    avg_win_rate = float(smart["win_rate"].mean())
    direction = "positive outcome pressure" if pressure >= 0 else "negative outcome pressure"
    confidence = "high" if avg_score > 0.7 and len(smart) >= 3 else "medium" if avg_score > 0.25 else "low"
    return {
        "action": "SHADOW_WATCH",
        "confidence": confidence,
        "reason": f"{len(smart)} historically positive wallets show {direction}",
        "avg_copy_score": avg_score,
        "avg_win_rate": avg_win_rate,
    }


def append_trades_snapshot(
    trades: pd.DataFrame,
    trades_csv: str = "data/market_trade_snapshots.csv",
) -> dict[str, Any]:
    """Append normalized trades to a local CSV and deduplicate best-effort."""
    if trades.empty:
        return {"rows": 0, "new_rows": 0}
    os.makedirs(os.path.dirname(trades_csv) or ".", exist_ok=True)
    try:
        existing = pd.read_csv(trades_csv)
        merged = pd.concat([existing, trades], ignore_index=True)
    except FileNotFoundError:
        existing = pd.DataFrame()
        merged = trades.copy()

    dedupe_cols = [col for col in ("transactionHash", "id") if col in merged.columns]
    if dedupe_cols:
        merged = merged.drop_duplicates(subset=dedupe_cols, keep="last")
    else:
        merged = merged.drop_duplicates(
            subset=["condition_id", "wallet_hash", "timestamp", "side", "outcome", "price", "size"],
            keep="last",
        )
    merged.to_csv(trades_csv, index=False)
    return {"rows": len(merged), "new_rows": max(0, len(merged) - len(existing))}
