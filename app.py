"""
Streamlit dashboard for the BTC five minute Polymarket paper trader.

The app is intentionally read only with respect to real markets. It displays:

1. The current Polymarket BTC five minute market.
2. The saved model guess for that current market.
3. The next market and upcoming market table for planning paper trades.
4. Local collector status so stale data is easy to spot.

The model is loaded from ``models/model.pkl`` through ``src.model_runtime``.
The dashboard never retrains the model during page rendering. Retraining is a
separate command line action so the UI stays fast and predictable.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from src.fetch import fetch_dashboard_snapshot
from src.model_runtime import clear_model_cache, predict_market_edge, score_market_edge
from src.predict import predict_from_market
from src.trading import PaperTrader


st.set_page_config(page_title="BTC Five Minute Paper Trader", layout="wide")


BLACK_GREEN_CSS = """
<style>
    :root {
        --bg: #020604;
        --panel: #07130d;
        --panel-alt: #0b1f14;
        --line: #174c2c;
        --green: #38ff7b;
        --green-soft: #8cffb2;
        --text: #e8fff0;
        --muted: #8aad9a;
        --danger: #ff5f7a;
    }

    .stApp {
        background: var(--bg);
        color: var(--text);
    }

    h1, h2, h3, h4, h5, h6, p, label, span, div {
        color: var(--text);
    }

    section[data-testid="stSidebar"] {
        background: #030a06;
        border-right: 1px solid var(--line);
    }

    div[data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        padding: 14px 16px;
        border-radius: 6px;
        box-shadow: inset 0 0 18px rgba(56, 255, 123, 0.05);
    }

    div[data-testid="stMetricLabel"] p {
        color: var(--muted);
        font-size: 0.82rem;
    }

    div[data-testid="stMetricValue"] {
        color: var(--green);
    }

    .stButton button {
        background: var(--green);
        color: #001f0b;
        border: 0;
        border-radius: 6px;
        font-weight: 700;
    }

    .stButton button:hover {
        background: var(--green-soft);
        color: #001f0b;
        border: 0;
    }

    .stDataFrame {
        border: 1px solid var(--line);
        border-radius: 6px;
    }

    div[data-testid="stAlert"] {
        background: var(--panel-alt);
        border: 1px solid var(--line);
        color: var(--text);
    }

    .green-panel {
        border: 1px solid var(--line);
        background: linear-gradient(180deg, rgba(9, 31, 18, 0.96), rgba(3, 10, 6, 0.96));
        border-radius: 6px;
        padding: 18px;
        margin: 8px 0 16px 0;
    }

    .small-muted {
        color: var(--muted);
        font-size: 0.88rem;
    }
</style>
"""


st.markdown(BLACK_GREEN_CSS, unsafe_allow_html=True)
st.title("BTC Five Minute Paper Trading Dashboard")


@st.cache_data(ttl=10, show_spinner=False)
def load_snapshot(periods):
    """Fetch ticker, current market, next market, and upcoming markets."""
    return fetch_dashboard_snapshot(periods=periods)


@st.cache_data(ttl=30, show_spinner=False)
def load_model_signal(market, edge_threshold):
    """Load the saved model and score a specific Polymarket market."""
    return predict_market_edge(market, edge_threshold=edge_threshold)


def format_price(value):
    """Format a nullable dollar value for display."""
    if value is None:
        return "N A"
    return f"${value:,.2f}"


def format_percent(value):
    """Format a nullable decimal probability for display."""
    if value is None:
        return "N A"
    return f"{value:.2%}"


def clean_text(value):
    """Return UI text without dash characters while preserving backend data."""
    if value is None:
        return "N A"
    return str(value).replace("-", " ")


def data_file_status(path):
    """Return row count and latest timestamp for a local collector CSV."""
    file_path = Path(path)
    if not file_path.exists():
        return {"path": path, "rows": 0, "latest": None}
    try:
        df = pd.read_csv(file_path)
    except Exception:
        return {"path": path, "rows": None, "latest": None}

    latest = None
    if not df.empty and "timestamp" in df.columns:
        latest = str(df["timestamp"].iloc[-1])
    return {"path": path, "rows": len(df), "latest": latest}


def market_row(market, model_signal=None, edge_threshold=0.03):
    """Convert a market dictionary into one display row."""
    if not market:
        return {}
    direction, probability = predict_from_market(market)
    edge = score_market_edge(market, model_signal, edge_threshold=edge_threshold)
    return {
        "window": clean_text(market.get("title")),
        "slug": clean_text(market.get("slug")),
        "ends": clean_text(market.get("end_date")),
        "up price": market.get("up_price"),
        "down price": market.get("down_price"),
        "market lean": direction,
        "market confidence": probability,
        "model p up": edge.get("model_probability_up"),
        "up edge": edge.get("up_edge"),
        "down edge": edge.get("down_edge"),
        "action": edge.get("action"),
        "liquidity": market.get("liquidity"),
        "volume": market.get("volume"),
    }


if "trader" not in st.session_state:
    st.session_state.trader = PaperTrader(market_mode="next")


with st.sidebar:
    st.header("Controls")
    market_mode = st.radio("Paper trade market", ["next", "current"], horizontal=True)
    upcoming_count = st.slider("Upcoming markets", min_value=4, max_value=24, value=8, step=4)
    edge_threshold = st.slider("Edge threshold", min_value=0.0, max_value=0.15, value=0.03, step=0.005)

    if st.session_state.trader.market_mode != market_mode:
        st.session_state.trader.market_mode = market_mode

    if st.button("Reset portfolio", width="stretch"):
        st.session_state.trader = PaperTrader(market_mode=market_mode)
        st.success("Portfolio reset")

    if st.button("Refresh markets", width="stretch"):
        load_snapshot.clear()
        load_model_signal.clear()

    if st.button("Reload model", width="stretch"):
        clear_model_cache()
        load_model_signal.clear()


snapshot = load_snapshot(upcoming_count)
ticker = snapshot.get("ticker") or {}
current_market = snapshot.get("current")
next_market = snapshot.get("next")
trade_market = next_market if market_mode == "next" else current_market

current_direction, current_market_probability = predict_from_market(current_market)
current_signal, current_edge = load_model_signal(current_market, edge_threshold)
trade_signal, trade_edge = load_model_signal(trade_market, edge_threshold)


st.markdown('<div class="green-panel">', unsafe_allow_html=True)
st.subheader("Current BTC Five Minute Market")
current_cols = st.columns(5)
current_cols[0].metric("BTC last", format_price(ticker.get("last_price")))
current_cols[1].metric("Polymarket lean", current_direction, format_percent(current_market_probability))
current_cols[2].metric("Model guess", current_signal.get("direction", "N A"), format_percent(current_signal.get("probability_up")))
current_cols[3].metric("UP price", f"{current_market['up_price']:.3f}" if current_market else "N A")
current_cols[4].metric("DOWN price", f"{current_market['down_price']:.3f}" if current_market else "N A")

if current_market:
    st.markdown(
        f'<p class="small-muted">{clean_text(current_market["title"])}  {clean_text(current_market["slug"])}  ends {clean_text(current_market["end_date"])}</p>',
        unsafe_allow_html=True,
    )
else:
    st.warning("No current BTC five minute market was found.")
st.markdown("</div>", unsafe_allow_html=True)


st.subheader("Model Edge For Current Market")
edge_cols = st.columns(5)
if current_signal.get("available"):
    metrics = current_signal.get("metrics", {})
    model_rows = metrics.get("rows", {})
    edge_cols[0].metric("Model status", "Loaded")
    edge_cols[1].metric("Action", current_edge.get("action", "SKIP"), format_percent(current_edge.get("edge")))
    edge_cols[2].metric("UP edge", format_percent(current_edge.get("up_edge")))
    edge_cols[3].metric("DOWN edge", format_percent(current_edge.get("down_edge")))
    edge_cols[4].metric("Feature count", model_rows.get("features", 0))
    st.caption(
        f"trained {clean_text(current_signal.get('trained_at'))}  latest candle {clean_text(current_signal.get('latest_candle'))}"
    )
else:
    edge_cols[0].metric("Model status", "Missing")
    st.warning(current_signal.get("reason", "No saved model signal is available."))


st.subheader("Paper Trade Target")
target_cols = st.columns(5)
target_direction, target_probability = predict_from_market(trade_market)
target_cols[0].metric("Target", market_mode.title())
target_cols[1].metric("Market lean", target_direction, format_percent(target_probability))
target_cols[2].metric("Model P UP", format_percent(trade_signal.get("probability_up")))
target_cols[3].metric("Action", trade_edge.get("action", "SKIP"))
target_cols[4].metric("Edge", format_percent(trade_edge.get("edge")))

if trade_market:
    st.caption(f"{clean_text(trade_market['title'])}  {clean_text(trade_market['slug'])}  ends {clean_text(trade_market['end_date'])}")
else:
    st.warning("No paper trade target market was found.")

if st.button("Run paper step", type="primary", disabled=trade_market is None):
    st.session_state.trader.step(market=trade_market, model_signal=trade_signal, edge_threshold=edge_threshold)
    st.success("Paper step recorded")


st.subheader("Portfolio")
trader = st.session_state.trader
portfolio_cols = st.columns(3)
portfolio_cols[0].metric("Portfolio value", f"${trader.portfolio_value:,.2f}")
portfolio_cols[1].metric("Cash", f"${trader.cash:,.2f}")
portfolio_cols[2].metric("Position", f"${trader.position:,.2f}")


st.subheader("Upcoming Markets")
upcoming = snapshot.get("upcoming") or []
if upcoming:
    market_df = pd.DataFrame([market_row(market, trade_signal, edge_threshold) for market in upcoming])
    st.dataframe(
        market_df,
        width="stretch",
        hide_index=True,
        column_config={
            "market confidence": st.column_config.ProgressColumn(
                "market confidence",
                format="%.2f",
                min_value=0,
                max_value=1,
            ),
            "model p up": st.column_config.ProgressColumn(
                "model P UP",
                format="%.2f",
                min_value=0,
                max_value=1,
            ),
            "up price": st.column_config.NumberColumn("UP", format="%.3f"),
            "down price": st.column_config.NumberColumn("DOWN", format="%.3f"),
            "up edge": st.column_config.NumberColumn("UP edge", format="%.3f"),
            "down edge": st.column_config.NumberColumn("DOWN edge", format="%.3f"),
        },
    )
else:
    st.info("No upcoming markets returned yet.")


with st.expander("Model breakdown"):
    model_probs = current_signal.get("model_probabilities", {})
    if model_probs:
        st.dataframe(
            pd.DataFrame([{"model": name, "probability up": prob} for name, prob in model_probs.items()]),
            width="stretch",
            hide_index=True,
            column_config={
                "probability up": st.column_config.ProgressColumn(
                    "P UP",
                    format="%.3f",
                    min_value=0,
                    max_value=1,
                )
            },
        )
    else:
        st.info("No model probability breakdown is available.")


with st.expander("Data collector status"):
    status_cols = st.columns(3)
    ticker_status = data_file_status("data/live_ticker.csv")
    polymarket_status = data_file_status("data/polymarket_markets.csv")
    trader_status = data_file_status("data/trader_signals.csv")
    market_status = data_file_status("data/market_data.csv")
    feature_status = data_file_status("data/features.csv")
    status_cols[0].metric("Ticker snapshots", ticker_status["rows"] or 0)
    status_cols[1].metric("Polymarket snapshots", polymarket_status["rows"] or 0)
    status_cols[2].metric("Trader signals", trader_status["rows"] or 0)
    st.metric("Training candles", market_status["rows"] or 0)
    st.metric("Feature rows", feature_status["rows"] or 0)
    st.caption(
        f"ticker latest {clean_text(ticker_status['latest'])}  "
        f"polymarket latest {clean_text(polymarket_status['latest'])}  "
        f"trader latest {clean_text(trader_status['latest'])}  "
        f"candle latest {clean_text(market_status['latest'])}  "
        f"features latest {clean_text(feature_status['latest'])}"
    )


with st.expander("Trader flow signal"):
    try:
        trader_signals = pd.read_csv("data/trader_signals.csv")
    except FileNotFoundError:
        trader_signals = pd.DataFrame()

    if trader_signals.empty:
        st.info("No trader flow snapshots collected yet.")
    else:
        latest_signal = trader_signals.tail(1).iloc[0]
        flow_cols = st.columns(5)
        flow_cols[0].metric("Trades", int(latest_signal.get("trader_trade_count", 0)))
        flow_cols[1].metric("Wallets", int(latest_signal.get("trader_wallet_count", 0)))
        flow_cols[2].metric("UP pressure", format_percent(latest_signal.get("trader_up_pressure")))
        flow_cols[3].metric("Smart UP pressure", format_percent(latest_signal.get("smart_up_pressure")))
        flow_cols[4].metric("Smart win rate", format_percent(latest_signal.get("smart_avg_win_rate")))
        try:
            leaders = pd.read_csv("data/trader_leaders.csv").tail(12)
        except FileNotFoundError:
            leaders = pd.DataFrame()
        if not leaders.empty:
            st.dataframe(
                leaders,
                width="stretch",
                hide_index=True,
                column_config={
                    "win_rate": st.column_config.ProgressColumn("win rate", format="%.2f", min_value=0, max_value=1),
                    "score": st.column_config.NumberColumn("score", format="%.2f"),
                    "realized_pnl": st.column_config.NumberColumn("realized pnl", format="%.2f"),
                    "total_value": st.column_config.NumberColumn("flow value", format="%.2f"),
                },
            )


st.subheader("Last 20 Trades")
if not trader.trades.empty:
    st.dataframe(trader.trades.tail(20), width="stretch", hide_index=True)
else:
    st.info("No trades yet")


st.subheader("Portfolio Chart")
if not trader.trades.empty:
    chart_df = trader.trades.copy()
    chart_df["timestamp"] = pd.to_datetime(chart_df["timestamp"])
    st.line_chart(chart_df.set_index("timestamp")["portfolio_value"])
