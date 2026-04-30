"""
Polymarket market snapshot utilities.

This module records public current and next BTC five minute market metadata.
Those snapshots become model features such as implied UP probability, price
spread, liquidity, and market confidence.

Historical resolved markets are intentionally not backfilled here. Fetching
closed markets after resolution can expose final outcome prices, which would
leak the answer into training. The safe approach is to collect these fields live
before the market resolves.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.fetch import fetch_current_market, fetch_next_market


def market_to_feature_row(market, market_role="current", collected_at=None):
    """Convert one normalized market dictionary into feature columns."""
    if not market:
        return None

    up_price = float(market.get("up_price") or 0.0)
    down_price = float(market.get("down_price") or 0.0)
    total = up_price + down_price
    implied_up = up_price / total if total else None
    implied_down = down_price / total if total else None

    return {
        "collected_at": collected_at or datetime.now(timezone.utc).isoformat(),
        "timestamp": pd.to_datetime(market.get("timestamp"), unit="s", utc=True).isoformat()
        if market.get("timestamp")
        else None,
        "market_role": market_role,
        "pm_slug": market.get("slug"),
        "pm_title": market.get("title"),
        "pm_end_date": market.get("end_date"),
        "pm_up_price": up_price,
        "pm_down_price": down_price,
        "pm_implied_up": implied_up,
        "pm_implied_down": implied_down,
        "pm_price_spread": abs(up_price - down_price),
        "pm_leader": 1 if up_price >= down_price else 0,
        "pm_volume": _safe_float(market.get("volume")),
        "pm_liquidity": _safe_float(market.get("liquidity")),
        "pm_event_id": market.get("event_id"),
        "pm_market_id": market.get("market_id"),
    }


def _safe_float(value):
    """Convert numeric API values while preserving missing fields."""
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_polymarket_snapshot():
    """Fetch current and next BTC market rows from Polymarket."""
    collected_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for role, market in (
        ("current", fetch_current_market("btc")),
        ("next", fetch_next_market("btc")),
    ):
        row = market_to_feature_row(market, market_role=role, collected_at=collected_at)
        if row:
            rows.append(row)
    return pd.DataFrame(rows)


def append_polymarket_snapshot(polymarket_csv="data/polymarket_markets.csv"):
    """Append and deduplicate live Polymarket market snapshot rows."""
    snapshot = fetch_polymarket_snapshot()
    if snapshot.empty:
        return {"rows": 0, "new_rows": 0, "latest": None}

    try:
        existing = pd.read_csv(polymarket_csv)
        merged = pd.concat([existing, snapshot], ignore_index=True)
    except FileNotFoundError:
        existing = pd.DataFrame()
        merged = snapshot

    merged["collected_at"] = pd.to_datetime(merged["collected_at"], utc=True, format="mixed")
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True, format="mixed")
    before = len(merged)
    merged = (
        merged.sort_values("collected_at")
        .drop_duplicates(subset=["timestamp", "market_role"], keep="last")
        .sort_values(["timestamp", "market_role"])
        .reset_index(drop=True)
    )
    merged.to_csv(polymarket_csv, index=False)
    return {
        "rows": len(merged),
        "new_rows": max(0, len(merged) - len(existing)),
        "deduped_rows": before - len(merged),
        "latest": str(merged["timestamp"].max()) if not merged.empty else None,
    }


def load_polymarket_features(polymarket_csv="data/polymarket_markets.csv"):
    """Load next market snapshot features for joining into candle data."""
    try:
        df = pd.read_csv(polymarket_csv)
    except FileNotFoundError:
        return pd.DataFrame()
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, format="mixed")
    df = df[df["market_role"] == "next"].copy()
    keep_cols = [
        "timestamp",
        "pm_up_price",
        "pm_down_price",
        "pm_implied_up",
        "pm_implied_down",
        "pm_price_spread",
        "pm_leader",
        "pm_volume",
        "pm_liquidity",
    ]
    return df[[col for col in keep_cols if col in df.columns]].drop_duplicates(
        subset=["timestamp"], keep="last"
    )


def add_market_features_to_latest(raw_df, market):
    """Attach one live market snapshot to the latest candle row."""
    if raw_df.empty or not market:
        return raw_df

    df = raw_df.copy()
    row = market_to_feature_row(market, market_role="next")
    if not row:
        return df

    for key, value in row.items():
        if key.startswith("pm_"):
            df.loc[df.index[-1], key] = value
    return df


def merge_polymarket_features(raw_df, polymarket_csv="data/polymarket_markets.csv"):
    """Merge collected Polymarket features into a candle dataframe."""
    pm = load_polymarket_features(polymarket_csv)
    if pm.empty:
        return raw_df

    df = raw_df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.merge(pm, on="timestamp", how="left")
