import pandas as pd
import numpy as np

def create_features(df):
    """
    Feature engineering for BTC 5-min market.
    """
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["price"] = df["price"].astype(float)

    # returns & log returns
    df["return"] = df["price"].pct_change()
    df["log_return"] = np.log1p(df["return"])

    # rolling features
    df["ma_3"] = df["price"].rolling(3).mean()
    df["ma_5"] = df["price"].rolling(5).mean()
    df["vol_3"] = df["log_return"].rolling(3).std()
    df["vol_5"] = df["log_return"].rolling(5).std()

    # lag features
    for lag in range(1, 4):
        df[f"lag_{lag}"] = df["log_return"].shift(lag)

    df.dropna(inplace=True)
    return df