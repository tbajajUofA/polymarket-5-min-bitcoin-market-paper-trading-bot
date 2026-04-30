"""
Feature engineering for BTC five minute prediction.

The model starts from Binance candle data and optionally receives live
Polymarket market snapshots plus public trader flow aggregates. Historical rows
will often lack Polymarket or trader fields because those are collected live
from now onward. For that reason this module only drops rows that are missing
core price derived features. Optional market intelligence columns are left as
missing values so sklearn imputers can handle them consistently.
"""

import pandas as pd
import numpy as np

def create_features(df):
    """
    Feature engineering for BTC 5-minute price data.
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    if "price" not in df.columns and "close" in df.columns:
        df["price"] = df["close"]

    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)

    df["price"] = df["price"].astype(float)

    if "pm_implied_up" in df.columns:
        # Polymarket price features describe what the market itself believes.
        # They are safe only when collected before the market resolves.
        df["pm_implied_up"] = pd.to_numeric(df["pm_implied_up"], errors="coerce")
        df["pm_implied_down"] = pd.to_numeric(df.get("pm_implied_down"), errors="coerce")
        df["pm_up_price"] = pd.to_numeric(df.get("pm_up_price"), errors="coerce")
        df["pm_down_price"] = pd.to_numeric(df.get("pm_down_price"), errors="coerce")
        df["pm_price_spread"] = pd.to_numeric(df.get("pm_price_spread"), errors="coerce")
        df["pm_missing"] = df["pm_implied_up"].isna().astype(int)
        df["pm_market_edge_vs_even"] = df["pm_implied_up"] - 0.5
        df["pm_market_confidence"] = (df["pm_implied_up"] - 0.5).abs()

    # returns & log returns
    df["return"] = df["price"].pct_change()
    df["log_return"] = np.log1p(df["return"])

    # rolling features
    df["ma_3"] = df["price"].rolling(3).mean()
    df["ma_5"] = df["price"].rolling(5).mean()
    df["vol_3"] = df["log_return"].rolling(3).std()
    df["vol_5"] = df["log_return"].rolling(5).std()
    df["range_pct"] = (df["high"] - df["low"]) / df["price"] if {"high", "low"}.issubset(df.columns) else 0
    df["close_position"] = (
        (df["close"] - df["low"]) / (df["high"] - df["low"]).replace(0, np.nan)
        if {"close", "high", "low"}.issubset(df.columns)
        else 0
    )
    if "volume" in df.columns:
        # Volume features help separate quiet random movement from traded moves.
        df["volume_change"] = pd.to_numeric(df["volume"], errors="coerce").pct_change()
        df["volume_ma_3"] = pd.to_numeric(df["volume"], errors="coerce").rolling(3).mean()
        df["volume_ma_12"] = pd.to_numeric(df["volume"], errors="coerce").rolling(12).mean()
    if {"taker_buy_base_volume", "volume"}.issubset(df.columns):
        # Binance taker buy share is a simple pressure proxy for recent flow.
        df["buy_volume_share"] = (
            pd.to_numeric(df["taker_buy_base_volume"], errors="coerce")
            / pd.to_numeric(df["volume"], errors="coerce").replace(0, np.nan)
        )

    # lag features
    for lag in range(1, 4):
        df[f"lag_{lag}"] = df["log_return"].shift(lag)

    required_feature_cols = [
        "return",
        "log_return",
        "ma_3",
        "ma_5",
        "vol_3",
        "vol_5",
        "lag_1",
        "lag_2",
        "lag_3",
    ]
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(subset=required_feature_cols, inplace=True)
    return df


def build_features(df):
    """Backward-compatible alias used by train.py."""
    return create_features(df)
