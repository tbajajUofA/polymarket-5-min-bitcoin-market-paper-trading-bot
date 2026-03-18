# app.py
import streamlit as st
from src.trading import PaperTrader
from src.predict import predict_for_market
import pandas as pd

st.set_page_config(page_title="BTC 5-min Paper Trader", layout="wide")
st.title("💹 BTC 5-min Paper Trading Dashboard")

trader = PaperTrader()

if st.button("Reset Portfolio"):
    trader = PaperTrader()
    st.success("Portfolio reset!")

direction, prob = predict_for_market()

st.subheader("📈 Latest BTC Prediction")
st.metric("Direction", direction, f"{prob:.2%} confidence")

trader.step()

st.subheader("💰 Portfolio Overview")
st.metric("Portfolio Value", f"${trader.portfolio_value:.2f}")
st.metric("Cash", f"${trader.cash:.2f}")
st.metric("Position", f"${trader.position:.2f}")

st.subheader("📝 Last 20 Trades")
if not trader.trades.empty:
    st.dataframe(trader.trades.tail(20))
else:
    st.info("No trades yet")

st.subheader("📊 Portfolio Chart")
if not trader.trades.empty:
    trader.trades["timestamp"] = pd.to_datetime(trader.trades["timestamp"])
    st.line_chart(trader.trades.set_index("timestamp")["portfolio_value"])