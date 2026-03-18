# src/fetch.py
import requests
import json
from datetime import datetime, timezone

GAMMA_API = "https://gamma-api.polymarket.com"

def get_current_5m_timestamp():
    now = datetime.now(timezone.utc)
    floored = now.replace(second=0, microsecond=0)
    floored = floored.replace(minute=(now.minute // 5) * 5)
    return int(floored.timestamp())

def fetch_market(asset="btc", timestamp=None):
    if timestamp is None:
        timestamp = get_current_5m_timestamp()
    slug = f"{asset}-updown-5m-{timestamp}"
    url = f"{GAMMA_API}/events/slug/{slug}"
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
        data = res.json()
        markets = data.get("markets", [])
        if not markets:
            return None
        m = markets[0]
        prices = json.loads(m.get("outcomePrices", '["0","0"]'))
        return {
            "asset": asset.upper(),
            "slug": slug,
            "up_price": float(prices[0]),
            "down_price": float(prices[1]),
            "volume": m.get("volume"),
            "end_date": m.get("endDate")
        }
    except requests.RequestException as e:
        print(f"[ERROR] fetch_market({asset}): {e}")
        return None