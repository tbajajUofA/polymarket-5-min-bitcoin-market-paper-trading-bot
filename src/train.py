"""
src/train.py

Train models that predict next-5-minute direction (UP / DOWN).

Design:
- Modular get_model(model_name) returning an sklearn-like estimator
- train_and_save(...) trains and saves model to models/model.pkl
- create target column (next period price movement)
- train/test split preserves time order by default
"""

from typing import Optional
import os
import joblib
import yaml
import logging

import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, confusion_matrix

from src.features import build_features

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_config(path: str = "config.yaml") -> dict:
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return {}


def get_model(name: str = "random_forest", random_state: int = 42):
    """Return a model instance given name."""
    name = name.lower()
    if name in ("random_forest", "rf"):
        return RandomForestClassifier(n_estimators=100, random_state=random_state, n_jobs=-1)
    if name in ("logistic_regression", "logistic"):
        return LogisticRegression(max_iter=1000, random_state=random_state)
    # placeholder for future neural net / xgboost
    raise ValueError(f"Unknown model: {name}")


def _create_target(feature_df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """
    Create binary target: 1 if price at t+horizon > price at t else 0.
    horizon measured in periods (assumes 1 period == 1 minute if features resampled to 1T).
    """
    df = feature_df.copy()
    df["future_price"] = df["price"].shift(-horizon)
    df["target"] = (df["future_price"] > df["price"]).astype(int)
    df = df.dropna(subset=["future_price"]).copy()
    return df


def train_and_save(raw_df: pd.DataFrame,
                   model_name: str = None,
                   config_path: str = "config.yaml",
                   save_path: str = None):
    """
    Train model and save to models/model.pkl.

    raw_df should be the DataFrame from fetch_historical_data (timestamp + price).
    """
    cfg = load_config(config_path)
    model_name = model_name or cfg.get("training", {}).get("model_name", "random_forest")
    test_size = cfg.get("training", {}).get("test_size", 0.2)
    random_state = cfg.get("training", {}).get("random_state", 42)
    save_path = save_path or cfg.get("models", {}).get("model_path", "models/model.pkl")

    logger.info("Building features...")
    features = build_features(raw_df)
    df = _create_target(features, horizon=5)  # 5-minute horizon

    X = df.drop(columns=["future_price", "target"])
    y = df["target"]

    # train/test split with preserve time order
    split_idx = int((1 - test_size) * len(X))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info("Got %d training rows and %d test rows", len(X_train), len(X_test))

    model = get_model(model_name, random_state=random_state)

    model.fit(X_train, y_train)

    # Evaluate
    preds = model.predict(X_test)
    probs = None
    try:
        probs = model.predict_proba(X_test)[:, 1]
    except Exception:
        probs = None

    acc = accuracy_score(y_test, preds)
    report = classification_report(y_test, preds)
    cm = confusion_matrix(y_test, preds)

    logger.info("Model %s accuracy: %.4f", model_name, acc)
    logger.info("Classification report:\n%s", report)
    logger.info("Confusion matrix:\n%s", cm)

    # Save model
    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    joblib.dump({"model": model, "columns": X.columns.tolist()}, save_path)
    logger.info("Saved model to %s", save_path)

    # Optionally return metrics
    return {"accuracy": acc, "report": report, "confusion_matrix": cm}


# If user wants to run from python -c "from src.train import train_and_save; ..."
# they can call train_and_save(...) manually. No top-level script execution here.