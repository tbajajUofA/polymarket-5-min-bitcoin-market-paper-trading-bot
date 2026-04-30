"""
Market and ticker fetch utilities.

This module is the boundary between the local bot and public market data APIs.
It has two jobs:

1. Discover Polymarket BTC five minute markets without hard coded slugs.
2. Fetch lightweight BTC ticker data for dashboard context.

Polymarket rolling BTC markets use predictable slugs:

    btc-updown-5m-<unix timestamp floored to five minutes>

The helper functions below build those slugs, fetch Gamma event metadata, and
normalize the response into a compact dictionary used by the prediction,
collector, and Streamlit layers. The normalized output deliberately includes
both outcome prices and token identifiers so later trading or orderbook code can
use the same object without another metadata lookup.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from datetime import datetime, timezone

import requests

GAMMA_API = "https://gamma-api.polymarket.com"
BINANCE_API = "https://api.binance.com"
BINANCE_US_API = "https://api.binance.us"
BTC_5M_SLUG_TEMPLATE = "{asset}-updown-5m-{timestamp}"

def get_current_5m_timestamp():
    """Return the current UTC timestamp floored to a five minute boundary."""
    now = datetime.now(timezone.utc)
    floored = now.replace(second=0, microsecond=0)
    floored = floored.replace(minute=(now.minute // 5) * 5)
    return int(floored.timestamp())

def _loads_json_list(value, default=None):
    """Parse Gamma JSON encoded list fields while tolerating missing values."""
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _parse_timestamp_from_slug(slug):
    """Extract the rolling market timestamp from a Polymarket slug."""
    try:
        return int(slug.rsplit("-", 1)[-1])
    except (AttributeError, TypeError, ValueError):
        return None


def _normalize_market(data, asset="btc"):
    """Convert a Gamma event payload into the bot's market dictionary shape."""
    markets = data.get("markets", [])
    if not markets:
        return None

    m = markets[0]
    outcomes = _loads_json_list(m.get("outcomes"), ["Up", "Down"])
    prices = _loads_json_list(m.get("outcomePrices"), ["0", "0"])
    token_ids = _loads_json_list(m.get("clobTokenIds"), [])
    slug = data.get("slug") or m.get("slug")
    timestamp = _parse_timestamp_from_slug(slug)

    outcome_map = {}
    for idx, name in enumerate(outcomes):
        price = float(prices[idx]) if idx < len(prices) else 0.0
        outcome_map[str(name).lower()] = {
            "name": name,
            "price": price,
            "token_id": token_ids[idx] if idx < len(token_ids) else None,
        }

    up = outcome_map.get("up", {"price": 0.0, "token_id": None})
    down = outcome_map.get("down", {"price": 0.0, "token_id": None})

    return {
        "asset": asset.upper(),
        "slug": slug,
        "timestamp": timestamp,
        "title": data.get("title") or m.get("question"),
        "question": m.get("question"),
        "active": bool(data.get("active") and m.get("active")),
        "closed": bool(data.get("closed") or m.get("closed")),
        "up_price": float(up["price"]),
        "down_price": float(down["price"]),
        "up_token_id": up.get("token_id"),
        "down_token_id": down.get("token_id"),
        "condition_id": m.get("conditionId"),
        "volume": m.get("volume"),
        "liquidity": m.get("liquidity") or data.get("liquidity"),
        "start_date": m.get("startDate") or data.get("startDate"),
        "end_date": m.get("endDate") or data.get("endDate"),
        "event_id": data.get("id"),
        "market_id": m.get("id"),
    }


def _fetch_market_by_slug(slug, asset="btc"):
    """Fetch one Polymarket event by slug and normalize its first market."""
    url = f"{GAMMA_API}/events/slug/{slug}"
    res = requests.get(url, timeout=5)
    if res.status_code == 404:
        return None
    res.raise_for_status()
    return _normalize_market(res.json(), asset=asset)


def discover_5m_markets(asset="btc", start_timestamp=None, periods=12, include_closed=False):
    """
    Return rolling 5-minute markets from start_timestamp forward.

    Polymarket BTC 5-minute slugs follow:
    btc-updown-5m-<unix timestamp floored to 5 minutes>
    so this does not require browsing/searching by title.
    """
    if start_timestamp is None:
        start_timestamp = get_current_5m_timestamp()

    slugs = [
        BTC_5M_SLUG_TEMPLATE.format(asset=asset, timestamp=start_timestamp + offset * 300)
        for offset in range(periods)
    ]

    markets = []
    with ThreadPoolExecutor(max_workers=min(8, max(1, periods))) as executor:
        futures = {executor.submit(_fetch_market_by_slug, slug, asset): slug for slug in slugs}
        for future in as_completed(futures):
            slug = futures[future]
            try:
                market = future.result()
            except requests.RequestException as e:
                print(f"[ERROR] discover_5m_markets({slug}): {e}")
                continue
            if market and (include_closed or not market["closed"]):
                markets.append(market)

    return sorted(markets, key=lambda item: item.get("timestamp") or 0)


def fetch_btc_ticker(symbol="BTCUSDT", source="binance"):
    """Fetch a lightweight BTC ticker snapshot for the dashboard."""
    base_url = BINANCE_US_API if source == "binance_us" else BINANCE_API
    url = f"{base_url}/api/v3/ticker/24hr"
    try:
        res = requests.get(url, params={"symbol": symbol}, timeout=5)
        res.raise_for_status()
        data = res.json()
        return {
            "symbol": data.get("symbol", symbol),
            "last_price": float(data["lastPrice"]),
            "price_change": float(data["priceChange"]),
            "price_change_percent": float(data["priceChangePercent"]),
            "high_price": float(data["highPrice"]),
            "low_price": float(data["lowPrice"]),
            "volume": float(data["volume"]),
            "quote_volume": float(data["quoteVolume"]),
        }
    except (requests.RequestException, KeyError, TypeError, ValueError) as e:
        print(f"[ERROR] fetch_btc_ticker({symbol}): {e}")
        return None


def fetch_dashboard_snapshot(asset="btc", periods=8, ticker_symbol="BTCUSDT"):
    """
    Fetch everything the dashboard needs with concurrent network calls.

    This keeps Streamlit responsive while grabbing the current market, next
    market, upcoming markets, and BTC ticker.
    """
    current_ts = get_current_5m_timestamp()
    tasks = {
        "current": lambda: fetch_current_market(asset),
        "next": lambda: fetch_next_market(asset),
        "upcoming": lambda: discover_5m_markets(asset, current_ts, periods),
        "ticker": lambda: fetch_btc_ticker(ticker_symbol),
    }
    snapshot = {}
    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                snapshot[name] = future.result()
            except Exception as e:
                print(f"[ERROR] fetch_dashboard_snapshot({name}): {e}")
                snapshot[name] = None

    return snapshot


def fetch_current_market(asset="btc"):
    """Return the current rolling BTC five minute market."""
    markets = discover_5m_markets(asset=asset, periods=1)
    return markets[0] if markets else None


def fetch_next_market(asset="btc", skip_current=True):
    """Return the next rolling BTC five minute market after the current slot."""
    start = get_current_5m_timestamp() + (300 if skip_current else 0)
    markets = discover_5m_markets(asset=asset, start_timestamp=start, periods=12)
    return markets[0] if markets else None


def fetch_market(asset="btc", timestamp=None, when="current"):
    """
    Fetch a BTC 5-minute market.

    Backward compatible:
    - fetch_market("btc") returns the current 5-minute market.
    - fetch_market("btc", timestamp=...) fetches that exact slug.

    New:
    - fetch_market("btc", when="next") returns the next available 5-minute market.
    """
    if timestamp is None:
        if when == "next":
            return fetch_next_market(asset=asset)
        if when == "current":
            return fetch_current_market(asset=asset)
        raise ValueError("when must be 'current' or 'next'")

    slug = BTC_5M_SLUG_TEMPLATE.format(asset=asset, timestamp=timestamp)
    try:
        return _fetch_market_by_slug(slug, asset=asset)
    except requests.RequestException as e:
        print(f"[ERROR] fetch_market({asset}): {e}")
        return None
