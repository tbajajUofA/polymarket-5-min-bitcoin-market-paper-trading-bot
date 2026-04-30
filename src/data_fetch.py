"""
Fetch BTC five minute training data.

The first-class source is Binance public klines because it gives clean,
no-key five minute OHLCV candles. CoinGecko is useful too, but its free chart
endpoint can shift granularity by date range; candles are the better training
primitive for this bot.

This module is used in two modes:

1. Historical backfills, such as fetching all candles from January 2025.
2. Runtime feature refreshes, where only the most recent candles are needed.

All rows are normalized to a stable schema with ``timestamp`` and ``price`` so
the feature builder and trainer do not depend on raw Binance field names.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
import requests

from src.features import build_features

logger = logging.getLogger(__name__)

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_US_URL = "https://api.binance.us/api/v3/klines"


def _to_milliseconds(value: datetime | str | int | None) -> int | None:
    """Convert accepted date inputs into Binance millisecond timestamps."""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


def _normalize_klines(rows: Iterable[list]) -> pd.DataFrame:
    """Normalize raw Binance kline arrays into typed candle rows."""
    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]
    df = pd.DataFrame(rows, columns=columns)
    if df.empty:
        return df

    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["price"] = df["close"]
    return df[
        [
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "price",
            "volume",
            "quote_asset_volume",
            "number_of_trades",
            "taker_buy_base_volume",
            "taker_buy_quote_volume",
        ]
    ].dropna(subset=["price"]).sort_values("timestamp").reset_index(drop=True)


def fetch_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    start: datetime | str | int | None = None,
    end: datetime | str | int | None = None,
    limit: int = 1000,
    pause_seconds: float = 0.2,
    base_url: str = BINANCE_KLINES_URL,
) -> pd.DataFrame:
    """
    Fetch historical candles from the Binance public API.

    If Binance.com is unavailable from your location, pass
    base_url=BINANCE_US_URL or use --source binance_us from the CLI.
    """
    start_ms = _to_milliseconds(start)
    end_ms = _to_milliseconds(end)
    rows: list[list] = []

    while True:
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        if start_ms is not None:
            params["startTime"] = start_ms
        if end_ms is not None:
            params["endTime"] = end_ms

        response = requests.get(base_url, params=params, timeout=20)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break

        rows.extend(batch)
        logger.info("Fetched %d candles; total=%d", len(batch), len(rows))

        last_open_time = int(batch[-1][0])
        next_start = last_open_time + 1
        if len(batch) < limit or (end_ms is not None and next_start >= end_ms):
            break
        if start_ms == next_start:
            break
        start_ms = next_start
        time.sleep(pause_seconds)

    return _normalize_klines(rows)


def fetch_recent_binance_klines(
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    limit: int = 300,
    base_url: str = BINANCE_KLINES_URL,
) -> pd.DataFrame:
    """Fetch the most recent candles in one bounded request."""
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(base_url, params=params, timeout=20)
    response.raise_for_status()
    return _normalize_klines(response.json())


def save_training_data(
    market_csv: str = "data/market_data.csv",
    features_csv: str = "data/features.csv",
    source: str = "binance",
    symbol: str = "BTCUSDT",
    interval: str = "5m",
    start: str | None = None,
    end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch historical candles, build features, and save both CSV files."""
    base_url = BINANCE_US_URL if source == "binance_us" else BINANCE_KLINES_URL
    raw = fetch_binance_klines(
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
        base_url=base_url,
    )
    features = build_features(raw)

    os.makedirs(os.path.dirname(market_csv) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(features_csv) or ".", exist_ok=True)
    raw.to_csv(market_csv, index=False)
    features.to_csv(features_csv, index=False)
    return raw, features


def main() -> None:
    """Command line entrypoint for historical candle collection."""
    parser = argparse.ArgumentParser(description="Fetch BTC 5-minute candles for model training.")
    parser.add_argument("--source", choices=["binance", "binance_us"], default="binance")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--start", default=None, help="UTC ISO date, for example 2026-01-01")
    parser.add_argument("--end", default=None, help="UTC ISO date, for example 2026-04-30")
    parser.add_argument("--market-csv", default="data/market_data.csv")
    parser.add_argument("--features-csv", default="data/features.csv")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    raw, features = save_training_data(
        market_csv=args.market_csv,
        features_csv=args.features_csv,
        source=args.source,
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
    )
    print(f"Saved {len(raw)} raw candles to {args.market_csv}")
    print(f"Saved {len(features)} feature rows to {args.features_csv}")


if __name__ == "__main__":
    main()
