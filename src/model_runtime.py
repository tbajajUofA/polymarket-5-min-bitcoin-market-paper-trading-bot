"""
Runtime loading and scoring for the saved model artifact.

Streamlit calls this module to score live Polymarket markets. The runtime path
must never train. It only loads ``models/model.pkl``, builds the latest feature
row from recent BTC candles plus live market signals, and returns probabilities
plus edge calculations.

Model artifacts are cached with ``lru_cache`` so repeated dashboard rerenders do
not reload joblib files from disk. The sidebar reload button clears this cache.
"""

import os
from functools import lru_cache

import joblib
import numpy as np

from src.data_fetch import fetch_recent_binance_klines
from src.features import build_features
from src.polymarket_data import add_market_features_to_latest
from src.trader_signals import add_trader_features_to_latest, build_trader_signal


DEFAULT_MODEL_PATH = "models/model.pkl"


@lru_cache(maxsize=4)
def load_model_artifact(path=DEFAULT_MODEL_PATH):
    """Load a saved joblib model artifact, or return None if it is missing."""
    if not os.path.exists(path):
        return None
    return joblib.load(path)


def clear_model_cache():
    """Clear cached model artifacts after a retrain or manual replacement."""
    load_model_artifact.cache_clear()


def _predict_model_proba(model, row):
    """Return P UP from any sklearn style classifier or decision function."""
    if hasattr(model, "predict_proba"):
        return float(model.predict_proba(row)[0, 1])
    score = float(model.decision_function(row)[0])
    return float(1 / (1 + np.exp(-score)))


def predict_btc_probability(model_path=DEFAULT_MODEL_PATH, candle_limit=300, market=None, trader_signal=None):
    """Build a live feature row and return the saved model probability."""
    artifact = load_model_artifact(model_path)
    if artifact is None:
        return {
            "available": False,
            "reason": f"No saved model found at {model_path}",
        }

    raw = fetch_recent_binance_klines(limit=candle_limit)
    raw = add_market_features_to_latest(raw, market)
    if trader_signal is None and market is not None:
        try:
            trader_signal, _ = build_trader_signal(market, trade_limit=150, top_wallets=8, closed_limit=50)
        except Exception:
            trader_signal = None
    raw = add_trader_features_to_latest(raw, trader_signal)
    features = build_features(raw)
    if features.empty:
        return {"available": False, "reason": "Recent candle features are empty"}

    columns = artifact["feature_columns"]
    row = features.reindex(columns=columns).tail(1)
    model_probs = {}
    weights = artifact.get("model_weights", {})
    weighted = []
    total_weight = 0.0
    for name, model in artifact["models"].items():
        prob = _predict_model_proba(model, row)
        weight = float(weights.get(name, 1.0))
        model_probs[name] = prob
        weighted.append(prob * weight)
        total_weight += weight

    probability_up = float(sum(weighted) / total_weight) if total_weight else float(np.mean(list(model_probs.values())))
    return {
        "available": True,
        "probability_up": probability_up,
        "probability_down": 1 - probability_up,
        "direction": "UP" if probability_up >= 0.5 else "DOWN",
        "confidence": max(probability_up, 1 - probability_up),
        "model_probabilities": model_probs,
        "trained_at": artifact.get("trained_at"),
        "metrics": artifact.get("metrics", {}),
        "latest_candle": str(raw["timestamp"].iloc[-1]) if not raw.empty and "timestamp" in raw.columns else None,
    }


def score_market_edge(market, signal, edge_threshold=0.03):
    """Compare model probability with Polymarket prices and choose an action."""
    if not market or not signal or not signal.get("available"):
        return {
            "available": False,
            "action": "SKIP",
            "reason": "Missing market or model signal",
        }

    p_up = float(signal["probability_up"])
    up_price = float(market["up_price"])
    down_price = float(market["down_price"])
    up_edge = p_up - up_price
    down_edge = (1 - p_up) - down_price

    if up_edge >= down_edge and up_edge >= edge_threshold:
        action = "BUY_UP"
        edge = up_edge
    elif down_edge > up_edge and down_edge >= edge_threshold:
        action = "BUY_DOWN"
        edge = down_edge
    else:
        action = "SKIP"
        edge = max(up_edge, down_edge)

    return {
        "available": True,
        "action": action,
        "edge": float(edge),
        "up_edge": float(up_edge),
        "down_edge": float(down_edge),
        "edge_threshold": edge_threshold,
        "model_probability_up": p_up,
        "market_up_price": up_price,
        "market_down_price": down_price,
    }


def predict_market_edge(market, model_path=DEFAULT_MODEL_PATH, edge_threshold=0.03):
    """Convenience wrapper that returns both model signal and market edge."""
    signal = predict_btc_probability(model_path=model_path, market=market)
    edge = score_market_edge(market, signal, edge_threshold=edge_threshold)
    return signal, edge
