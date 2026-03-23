# BTC 5-Min Paper Trading Bot

A **paper trading bot for Bitcoin (BTC)** using 5-minute markets from Polymarket. It predicts short-term price movements and simulates trades without using real money.

---

## Features

- Fetch BTC 5-minute markets from Polymarket Gamma API
- Feature engineering: returns, log returns, rolling averages, volatility, lag features
- Predict direction (UP / DOWN) using ML models (Random Forest by default)
- Paper trading simulation with cash, position, and portfolio value
- Live dashboard with predictions, trades, and portfolio chart
- Fully plug-and-play for BTC 5-min marketsCsAA

---

## Project Structure
```
poly/
│── app.py              # Streamlit dashboard (root)
│── config.yaml         # Bot configuration (markets, data paths, thresholds)
│── src/
│   ├── __init__.py     # Empty, marks src as Python module
│   ├── fetch.py        # Fetches BTC 5-min market data from Gamma API
│   ├── features.py     # Feature engineering for ML models
│   ├── predict.py      # Predict BTC direction (UP/DOWN) using features
│   ├── trading.py      # Paper trading logic, manages portfolio & trades
│   ├── load_config.py  # Loads config.yaml safely
│   └── train.py        # Train ML model (Random Forest / Logistic Regression)
│── data/               # Stores market data, features, and trades
│── models/             # Stores trained ML models
│── requirements.txt    # Python dependencies
```

---

## Installation

1. **Clone the repo:**
```bash
git clone <repo_url>
cd polymarket-5-min-bot-trader
```

2. **Create a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

---

## Configuration (`config.yaml`)
```yaml
markets:
  default_market: "btc-updown-5m-1773817200"  # BTC 5-min slug
  api_base: "https://gamma-api.polymarket.com"

data:
  market_csv: "data/market_data.csv"
  features_csv: "data/features.csv"
  trades_csv: "data/trades.csv"

models:
  model_path: "models/model.pkl"

training:
  model_name: "random_forest"
  test_size: 0.2
  random_state: 42

trading:
  starting_cash: 10000.0
  buy_threshold: 0.55
  sell_threshold: 0.5
```

> **Note:** For automated trading across new 5-min periods, you can later implement dynamic slug discovery.

---

## File Documentation

### `src/fetch.py`

Handles all data fetching from the Polymarket Gamma API.

**Functions:**

- `get_current_5m_timestamp()` — Returns current UTC timestamp floored to nearest 5 minutes.
- `fetch_market(asset="btc", timestamp=None)` — Fetches market data for BTC 5-min. Returns a dictionary with: `asset`, `slug`, `up_price`, `down_price`, `volume`, `end_date`.

---

### `src/features.py`

Performs feature engineering on market price data.

**Features include:**

- `return`, `log_return`
- Rolling averages: `ma_3`, `ma_5`
- Volatility: `vol_3`, `vol_5`
- Lagged features: `lag_1`, `lag_2`, `lag_3`

**Output:** Cleaned pandas DataFrame ready for ML models.

---

### `src/load_config.py`

Safely loads `config.yaml`. Returns a dictionary with all configuration parameters. Raises errors if the file is missing or YAML is invalid.

---

### `src/predict.py`

Uses latest market data to predict BTC direction.

- Predicts `UP` if `up_price > down_price`
- Returns a `(direction, probability)` tuple
- Fully self-contained — no circular imports

---

### `src/trading.py`

Implements paper trading logic.

**Tracks:**
- Cash
- Position
- Portfolio value
- Trade history

`PaperTrader.step()` executes one trading step: calls `predict_for_market()`, buys if probability > threshold, sells otherwise.

---

### `src/train.py`

Trains an ML model to predict next-5-minute BTC direction.

- Modular: `get_model(model_name)` returns an sklearn-like estimator (Random Forest or Logistic Regression)
- Creates binary target based on future price movement
- Handles train/test split, evaluation metrics, and saves model to `models/model.pkl`

---

### `app.py`

Streamlit dashboard for live monitoring.

**Displays:**
- Latest BTC 5-min prediction
- Portfolio overview
- Last 20 trades
- Portfolio value chart

Includes a **Reset Portfolio** button. Fully plug-and-play with BTC 5-min markets.

---

## Running the Bot
```bash
streamlit run app.py
```

- Open the URL in your browser (default: `http://localhost:8501`)
- The dashboard shows live predictions and the portfolio chart
- Each "step" simulates trading on the latest BTC 5-min market

---

## Notes for Later

- `fetch.py` uses slug-based fetching → ensures 5-min markets are always correctly retrieved
- `predict.py` can be upgraded to Random Forest or Neural Network in the future
- `trading.py` is paper-only — no real money trading
- `features.py` prepares data for ML training with rolling statistics
- `train.py` handles the full model lifecycle: features → train → save → evaluate
