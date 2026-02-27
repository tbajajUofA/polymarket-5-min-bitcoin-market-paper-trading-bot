import requests
from datetime import datetime, timezone

GAMMA = "https://gamma-api.polymarket.com"
ASSETS = ["btc", "eth", "sol", "xrp"]

def get_current_5m_timestamp():
    now = datetime.now(timezone.utc)
    # round down to nearest 5 minutes
    floored = now.replace(second=0, microsecond=0)
    floored = floored.replace(minute=(now.minute // 5) * 5)
    return int(floored.timestamp())

def fetch_market(asset, timestamp):
    slug = f"{asset}-updown-5m-{timestamp}"
    url = f"{GAMMA}/events/slug/{slug}"
    res = requests.get(url)
    if res.status_code != 200:
        return None
    data = res.json()
    markets = data.get("markets", [])
    if not markets:
        return None
    m = markets[0]
    prices = eval(m["outcomePrices"])  # ["0.52", "0.48"]
    return {
        "asset": asset.upper(),
        "slug": slug,
        "up_price": float(prices[0]),
        "down_price": float(prices[1]),
        "volume": m.get("volume"),
        "end_date": m.get("endDate")
    }

ts = get_current_5m_timestamp()
for asset in ASSETS:
    result = fetch_market(asset, ts)
    if result:
        print(f"{result['asset']}: UP={result['up_price']:.2f}  DOWN={result['down_price']:.2f}  Vol={result['volume']}")
    else:
        print(f"{asset.upper()}: market not found")