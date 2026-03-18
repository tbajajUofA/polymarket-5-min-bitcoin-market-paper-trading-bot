# src/predict.py
from src.fetch import fetch_market

def predict_for_market():
    """
    Dummy prediction: predicts UP if up_price > down_price
    """
    market = fetch_market("btc")
    if not market:
        return "N/A", 0.0
    # simple random forest placeholder logic
    up = market["up_price"]
    down = market["down_price"]
    if up >= down:
        return "UP", up / (up + down)
    else:
        return "DOWN", down / (up + down)