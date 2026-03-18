# src/trading.py
import pandas as pd
from datetime import datetime
from src.predict import predict_for_market

class PaperTrader:
    def __init__(self, starting_cash=10000):
        self.cash = starting_cash
        self.position = 0
        self.portfolio_value = starting_cash
        self.trades = pd.DataFrame(columns=["timestamp", "direction", "price", "portfolio_value"])

    def step(self):
        direction, prob = predict_for_market()
        price = 1.0  # normalized for simplicity
        now = datetime.utcnow()
        if direction == "UP" and prob > 0.55:
            self.position += self.cash
            self.cash = 0
        elif direction == "DOWN":
            self.cash += self.position
            self.position = 0
        self.portfolio_value = self.cash + self.position
        self.trades.loc[len(self.trades)] = [now, direction, price, self.portfolio_value]