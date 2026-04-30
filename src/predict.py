"""
Prediction helpers.

There are two prediction paths:

1. ``predict_from_market`` is the simple market implied baseline. It looks only
   at Polymarket UP and DOWN prices.
2. ``predict_model_for_market`` loads the saved sklearn artifact through
   ``model_runtime`` and compares the model probability with Polymarket prices.

Keeping both paths is useful because the market implied baseline is an always
available sanity check when the saved model is missing or stale.
"""

from src.fetch import fetch_market
from src.model_runtime import predict_market_edge

def predict_from_market(market):
    """Return the Polymarket implied direction and confidence for one market."""
    if not market:
        return "N/A", 0.0

    up = market["up_price"]
    down = market["down_price"]
    total = up + down
    if total <= 0:
        return "N/A", 0.0
    if up >= down:
        return "UP", up / total
    return "DOWN", down / total


def predict_for_market(when="current", market=None):
    """
    Dummy prediction: predicts UP if up_price > down_price
    """
    market = market or fetch_market("btc", when=when)
    return predict_from_market(market)


def predict_model_for_market(when="current", market=None, edge_threshold=0.03):
    """Return saved model signal and edge calculation for a market."""
    market = market or fetch_market("btc", when=when)
    return predict_market_edge(market, edge_threshold=edge_threshold)
