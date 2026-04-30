"""
Train and save a BTC 5-minute ensemble model.

The saved artifact is designed for runtime loading by Streamlit. The app should
never retrain on page load; it only reads models/model.pkl.

The trainer supports both a full ensemble and a single logistic baseline. The
current saved production artifact may intentionally contain only
``baseline_logistic`` when we want a small, interpretable benchmark. Every
artifact stores feature columns, fitted models, model weights, and evaluation
metrics so Streamlit can display model state without retraining.
"""

import argparse
import logging
import os
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
import yaml

from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from src.features import build_features
from src.polymarket_data import merge_polymarket_features
from src.trader_signals import merge_trader_features

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def load_config(path: str = "config.yaml") -> dict:
    """Load optional YAML training configuration."""
    if os.path.exists(path):
        with open(path, "r") as f:
            return yaml.safe_load(f)
    return {}


def _create_target(feature_df: pd.DataFrame, horizon: int = 1) -> pd.DataFrame:
    """Create target=1 when price is higher after `horizon` periods."""
    df = feature_df.copy()
    df["future_price"] = df["price"].shift(-horizon)
    df["target"] = (df["future_price"] > df["price"]).astype(int)
    return df.dropna(subset=["future_price"]).copy()


def _prepare_xy(raw_df: pd.DataFrame, horizon: int):
    """Build features, target, numeric X matrix, and aligned labels."""
    features = build_features(raw_df)
    df = _create_target(features, horizon=horizon)
    drop_cols = ["future_price", "target", "timestamp"]
    X = df.drop(columns=[col for col in drop_cols if col in df.columns])
    X = X.select_dtypes(include=["number", "bool"]).copy()
    y = df["target"].astype(int)
    return X, y, df


def _chronological_split(X, y, test_size):
    """Split without shuffling so test data is later than train data."""
    split_idx = int((1 - test_size) * len(X))
    split_idx = max(1, min(split_idx, len(X) - 1))
    return X.iloc[:split_idx], X.iloc[split_idx:], y.iloc[:split_idx], y.iloc[split_idx:]


def _model_suite(random_state: int):
    """Return all supported sklearn model pipelines."""
    return {
        "baseline_logistic": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                ("scaler", StandardScaler()),
                ("model", LogisticRegression(max_iter=2000, random_state=random_state)),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        min_samples_leaf=20,
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "extra_trees": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                (
                    "model",
                    ExtraTreesClassifier(
                        n_estimators=300,
                        min_samples_leaf=20,
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "gradient_boosting": Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        max_iter=250,
                        learning_rate=0.04,
                        l2_regularization=0.05,
                        random_state=random_state,
                    ),
                ),
            ]
        ),
    }


def _predict_proba_up(model, X):
    """Return class one probabilities for models with different APIs."""
    if hasattr(model, "predict_proba"):
        return model.predict_proba(X)[:, 1]
    scores = model.decision_function(X)
    return 1 / (1 + np.exp(-scores))


def _score_probabilities(y_true, proba):
    """Compute model diagnostics used by CLI output and Streamlit."""
    preds = (proba >= 0.5).astype(int)
    scores = {
        "accuracy": float(accuracy_score(y_true, preds)),
        "log_loss": float(log_loss(y_true, np.clip(proba, 1e-6, 1 - 1e-6))),
        "confusion_matrix": confusion_matrix(y_true, preds).tolist(),
        "classification_report": classification_report(y_true, preds, zero_division=0),
    }
    try:
        scores["roc_auc"] = float(roc_auc_score(y_true, proba))
    except ValueError:
        scores["roc_auc"] = None
    return scores


def train_and_save(
    raw_df: pd.DataFrame,
    model_name: str = None,
    config_path: str = "config.yaml",
    save_path: str = None,
    polymarket_csv: str = "data/polymarket_markets.csv",
    trader_signals_csv: str = "data/trader_signals.csv",
):
    """
    Train a probability ensemble and save it to models/model.pkl.

    `model_name` is accepted for backward compatibility. The default trains the
    full ensemble; passing a single known name trains only that model.
    """
    cfg = load_config(config_path)
    test_size = cfg.get("training", {}).get("test_size", 0.2)
    random_state = cfg.get("training", {}).get("random_state", 42)
    horizon = cfg.get("training", {}).get("horizon_periods", 1)
    save_path = save_path or cfg.get("models", {}).get("model_path", "models/model.pkl")

    raw_df = merge_polymarket_features(raw_df, polymarket_csv=polymarket_csv)
    raw_df = merge_trader_features(raw_df, signals_csv=trader_signals_csv)
    X, y, feature_df = _prepare_xy(raw_df, horizon=horizon)
    if len(X) < 200:
        raise ValueError(f"Need at least 200 feature rows to train safely, got {len(X)}")

    X_train, X_test, y_train, y_test = _chronological_split(X, y, test_size)
    logger.info("Training rows=%d test rows=%d features=%d", len(X_train), len(X_test), len(X.columns))

    models = _model_suite(random_state)
    if model_name and model_name not in ("ensemble", "all"):
        if model_name not in models:
            raise ValueError(f"Unknown model: {model_name}. Choose one of {sorted(models)} or ensemble.")
        models = {model_name: models[model_name]}

    fitted_models = {}
    model_scores = {}
    test_probabilities = {}
    for name, model in models.items():
        logger.info("Fitting %s", name)
        model.fit(X_train, y_train)
        proba = _predict_proba_up(model, X_test)
        fitted_models[name] = model
        test_probabilities[name] = proba
        model_scores[name] = _score_probabilities(y_test, proba)
        logger.info("%s accuracy=%.4f log_loss=%.4f", name, model_scores[name]["accuracy"], model_scores[name]["log_loss"])

    if len(X_train) >= 1000 and (not model_name or model_name in ("ensemble", "all")):
        recent_rows = min(len(X_train), 2500)
        recent_model = Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", keep_empty_features=True)),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=250,
                        min_samples_leaf=10,
                        random_state=random_state + 7,
                        n_jobs=-1,
                    ),
                ),
            ]
        )
        recent_model.fit(X_train.tail(recent_rows), y_train.tail(recent_rows))
        proba = _predict_proba_up(recent_model, X_test)
        fitted_models["recent_random_forest"] = recent_model
        test_probabilities["recent_random_forest"] = proba
        model_scores["recent_random_forest"] = _score_probabilities(y_test, proba)

    ensemble_proba = np.mean(list(test_probabilities.values()), axis=0)
    ensemble_scores = _score_probabilities(y_test, ensemble_proba)

    artifact = {
        "artifact_version": 2,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "target": "next_5m_btc_up",
        "horizon_periods": horizon,
        "feature_columns": X.columns.tolist(),
        "models": fitted_models,
        "model_weights": {name: 1.0 for name in fitted_models},
        "metrics": {
            "ensemble": ensemble_scores,
            "models": model_scores,
            "rows": {"train": len(X_train), "test": len(X_test), "features": len(X.columns)},
            "feature_start": str(feature_df["timestamp"].min()) if "timestamp" in feature_df.columns else None,
            "feature_end": str(feature_df["timestamp"].max()) if "timestamp" in feature_df.columns else None,
        },
    }

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    joblib.dump(artifact, save_path)
    logger.info("Saved ensemble artifact to %s", save_path)
    return artifact["metrics"]


def main() -> None:
    """Command line entrypoint for model training."""
    parser = argparse.ArgumentParser(description="Train the BTC direction ensemble from CSV data.")
    parser.add_argument("--input", default="data/market_data.csv", help="CSV with timestamp and price/close columns.")
    parser.add_argument("--model-name", default="ensemble")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--save-path", default=None)
    parser.add_argument("--polymarket-input", default="data/polymarket_markets.csv")
    parser.add_argument("--trader-signals-input", default="data/trader_signals.csv")
    args = parser.parse_args()

    raw_df = pd.read_csv(args.input)
    metrics = train_and_save(
        raw_df,
        model_name=args.model_name,
        config_path=args.config,
        save_path=args.save_path,
        polymarket_csv=args.polymarket_input,
        trader_signals_csv=args.trader_signals_input,
    )
    print(f"ensemble_accuracy={metrics['ensemble']['accuracy']:.4f}")
    print(f"ensemble_log_loss={metrics['ensemble']['log_loss']:.4f}")
    print(metrics["ensemble"]["classification_report"])


if __name__ == "__main__":
    main()
