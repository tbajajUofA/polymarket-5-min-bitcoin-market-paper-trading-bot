"""
Paper trading state machine.

This module never places real orders. It records a simplified simulated
portfolio so the dashboard can evaluate whether model signals would have led to
reasonable paper decisions. The current implementation uses normalized position
value rather than a full Polymarket fill simulator. That keeps the first loop
simple while the data and signal pipeline are still evolving.
"""

from datetime import datetime

import pandas as pd

from src.model_runtime import score_market_edge
from src.predict import predict_for_market

class PaperTrader:
    """In memory paper trader used by Streamlit session state."""

    def __init__(self, starting_cash=10000, market_mode="next"):
        """Create a fresh simulated portfolio."""
        self.cash = starting_cash
        self.position = 0
        self.portfolio_value = starting_cash
        self.market_mode = market_mode
        self.trades = pd.DataFrame(
            columns=[
                "timestamp",
                "market_slug",
                "direction",
                "model_probability_up",
                "edge",
                "action",
                "price",
                "portfolio_value",
            ]
        )

    def step(self, market=None, model_signal=None, edge_threshold=0.03):
        """Record one paper decision using either model edge or market baseline."""
        from src.fetch import fetch_market

        market = market or fetch_market("btc", when=self.market_mode)
        if model_signal and model_signal.get("available"):
            direction = model_signal["direction"]
            prob = model_signal["confidence"]
            edge = score_market_edge(market, model_signal, edge_threshold=edge_threshold)
            action = edge["action"]
            model_probability_up = model_signal["probability_up"]
            trade_edge = edge.get("edge")
        else:
            direction, prob = predict_for_market(when=self.market_mode, market=market)
            action = "BUY_UP" if direction == "UP" and prob > 0.55 else "SELL_OR_SKIP"
            model_probability_up = None
            trade_edge = None

        price = 1.0  # normalized for simplicity
        now = datetime.utcnow()
        if action == "BUY_UP" or (direction == "UP" and prob > 0.55):
            self.position += self.cash
            self.cash = 0
        elif action == "BUY_DOWN" or direction == "DOWN":
            self.cash += self.position
            self.position = 0
        self.portfolio_value = self.cash + self.position
        self.trades.loc[len(self.trades)] = [
            now,
            market["slug"] if market else None,
            direction,
            model_probability_up,
            trade_edge,
            action,
            price,
            self.portfolio_value,
        ]
