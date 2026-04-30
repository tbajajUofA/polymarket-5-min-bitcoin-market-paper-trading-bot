"""
Continuously collect BTC market data for training.

This uses public APIs rather than brittle webpage scraping:

1. Binance ticker snapshots go to ``data/live_ticker.csv``.
2. Recent five minute candles are merged into ``data/market_data.csv``.
3. Polymarket current and next market snapshots are recorded.
4. Public trader flow is aggregated into anonymous wallet features.
5. Features are rebuilt into ``data/features.csv``.
6. Optional scheduled retraining refreshes ``models/model.pkl``.

The collector is safe to run repeatedly. Candle rows are deduplicated by
timestamp, and market plus trader snapshots keep the latest row for each market
slot. The collector does not execute trades.
"""

from __future__ import annotations

import argparse
import logging
import os
import time
from datetime import datetime, timezone

import pandas as pd

from src.data_fetch import BINANCE_KLINES_URL, BINANCE_US_URL, fetch_recent_binance_klines
from src.features import build_features
from src.fetch import fetch_btc_ticker, fetch_next_market
from src.polymarket_data import append_polymarket_snapshot, merge_polymarket_features
from src.train import train_and_save
from src.trader_signals import append_trader_signal, merge_trader_features

logger = logging.getLogger(__name__)


def _utc_now_iso():
    """Return the current UTC time as an ISO string."""
    return datetime.now(timezone.utc).isoformat()


def _base_url(source):
    """Map a source name to the Binance compatible kline base URL."""
    return BINANCE_US_URL if source == "binance_us" else BINANCE_KLINES_URL


def append_ticker_snapshot(ticker_csv="data/live_ticker.csv", symbol="BTCUSDT", source="binance"):
    """Append one BTC ticker snapshot to the local ticker CSV."""
    ticker = fetch_btc_ticker(symbol=symbol, source=source)
    if not ticker:
        return None

    row = {"timestamp": _utc_now_iso(), **ticker}
    os.makedirs(os.path.dirname(ticker_csv) or ".", exist_ok=True)
    pd.DataFrame([row]).to_csv(
        ticker_csv,
        mode="a",
        index=False,
        header=not os.path.exists(ticker_csv),
    )
    return row


def merge_recent_candles(
    market_csv="data/market_data.csv",
    features_csv="data/features.csv",
    symbol="BTCUSDT",
    interval="5m",
    source="binance",
    limit=300,
    polymarket_csv="data/polymarket_markets.csv",
    trader_signals_csv="data/trader_signals.csv",
):
    """Merge recent candles and rebuild features with optional external signals."""
    recent = fetch_recent_binance_klines(
        symbol=symbol,
        interval=interval,
        limit=limit,
        base_url=_base_url(source),
    )
    if recent.empty:
        return {"rows": 0, "new_rows": 0}

    os.makedirs(os.path.dirname(market_csv) or ".", exist_ok=True)
    if os.path.exists(market_csv):
        existing = pd.read_csv(market_csv)
        merged = pd.concat([existing, recent], ignore_index=True)
    else:
        existing = pd.DataFrame()
        merged = recent

    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    before = len(merged)
    merged = (
        merged.drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    new_rows = len(merged) - len(existing)
    merged.to_csv(market_csv, index=False)

    feature_input = merge_polymarket_features(merged, polymarket_csv=polymarket_csv)
    feature_input = merge_trader_features(feature_input, signals_csv=trader_signals_csv)
    features = build_features(feature_input)
    os.makedirs(os.path.dirname(features_csv) or ".", exist_ok=True)
    features.to_csv(features_csv, index=False)

    return {
        "rows": len(merged),
        "new_rows": max(0, new_rows),
        "deduped_rows": before - len(merged),
        "latest_candle": str(merged["timestamp"].iloc[-1]) if not merged.empty else None,
    }


def collect_once(
    market_csv="data/market_data.csv",
    features_csv="data/features.csv",
    ticker_csv="data/live_ticker.csv",
    polymarket_csv="data/polymarket_markets.csv",
    trader_signals_csv="data/trader_signals.csv",
    trader_leaders_csv="data/trader_leaders.csv",
    source="binance",
    symbol="BTCUSDT",
    interval="5m",
    candle_limit=300,
):
    """Run one collector cycle and return a summary dictionary."""
    ticker = append_ticker_snapshot(ticker_csv=ticker_csv, symbol=symbol, source=source)
    polymarket = append_polymarket_snapshot(polymarket_csv=polymarket_csv)
    trader_signal = append_trader_signal(
        fetch_next_market("btc"),
        signals_csv=trader_signals_csv,
        leaders_csv=trader_leaders_csv,
    )
    candles = merge_recent_candles(
        market_csv=market_csv,
        features_csv=features_csv,
        symbol=symbol,
        interval=interval,
        source=source,
        limit=candle_limit,
        polymarket_csv=polymarket_csv,
        trader_signals_csv=trader_signals_csv,
    )
    return {"ticker": ticker, "polymarket": polymarket, "trader_signal": trader_signal, "candles": candles}


def run_collector(
    poll_seconds=60,
    retrain_minutes=None,
    market_csv="data/market_data.csv",
    features_csv="data/features.csv",
    ticker_csv="data/live_ticker.csv",
    polymarket_csv="data/polymarket_markets.csv",
    trader_signals_csv="data/trader_signals.csv",
    trader_leaders_csv="data/trader_leaders.csv",
    model_path="models/model.pkl",
    source="binance",
    symbol="BTCUSDT",
    interval="5m",
    candle_limit=300,
):
    """Run the collector loop until interrupted."""
    last_retrain = 0.0
    while True:
        try:
            result = collect_once(
                market_csv=market_csv,
                features_csv=features_csv,
                ticker_csv=ticker_csv,
                polymarket_csv=polymarket_csv,
                trader_signals_csv=trader_signals_csv,
                trader_leaders_csv=trader_leaders_csv,
                source=source,
                symbol=symbol,
                interval=interval,
                candle_limit=candle_limit,
            )
            logger.info(
                "Collected ticker=%s rows=%s new_rows=%s latest=%s",
                bool(result["ticker"]),
                result["candles"].get("rows"),
                result["candles"].get("new_rows"),
                result["candles"].get("latest_candle"),
            )

            if retrain_minutes:
                due = time.time() - last_retrain >= retrain_minutes * 60
                if due and os.path.exists(market_csv):
                    logger.info("Retraining ensemble model")
                    raw = pd.read_csv(market_csv)
                    train_and_save(
                        raw,
                        model_name="ensemble",
                        save_path=model_path,
                        polymarket_csv=polymarket_csv,
                        trader_signals_csv=trader_signals_csv,
                    )
                    last_retrain = time.time()
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            logger.exception("Collector cycle failed: %s", exc)

        time.sleep(poll_seconds)


def main():
    """Command line entrypoint for one shot or continuous collection."""
    parser = argparse.ArgumentParser(description="Continuously collect BTC data for the model.")
    parser.add_argument("--once", action="store_true", help="Run one collection cycle and exit.")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--retrain-minutes", type=int, default=None)
    parser.add_argument("--source", choices=["binance", "binance_us"], default="binance")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="5m")
    parser.add_argument("--candle-limit", type=int, default=300)
    parser.add_argument("--market-csv", default="data/market_data.csv")
    parser.add_argument("--features-csv", default="data/features.csv")
    parser.add_argument("--ticker-csv", default="data/live_ticker.csv")
    parser.add_argument("--polymarket-csv", default="data/polymarket_markets.csv")
    parser.add_argument("--trader-signals-csv", default="data/trader_signals.csv")
    parser.add_argument("--trader-leaders-csv", default="data/trader_leaders.csv")
    parser.add_argument("--model-path", default="models/model.pkl")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s:%(name)s:%(message)s")

    if args.once:
        result = collect_once(
            market_csv=args.market_csv,
            features_csv=args.features_csv,
            ticker_csv=args.ticker_csv,
            polymarket_csv=args.polymarket_csv,
            trader_signals_csv=args.trader_signals_csv,
            trader_leaders_csv=args.trader_leaders_csv,
            source=args.source,
            symbol=args.symbol,
            interval=args.interval,
            candle_limit=args.candle_limit,
        )
        print(result)
        return

    run_collector(
        poll_seconds=args.poll_seconds,
        retrain_minutes=args.retrain_minutes,
        market_csv=args.market_csv,
        features_csv=args.features_csv,
        ticker_csv=args.ticker_csv,
        polymarket_csv=args.polymarket_csv,
        trader_signals_csv=args.trader_signals_csv,
        trader_leaders_csv=args.trader_leaders_csv,
        model_path=args.model_path,
        source=args.source,
        symbol=args.symbol,
        interval=args.interval,
        candle_limit=args.candle_limit,
    )


if __name__ == "__main__":
    main()
