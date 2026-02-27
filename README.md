# Polymarket Trading Bot

A machine learning bot that predicts Polymarket outcomes using historical price data and time series analysis. In particular, the price of BitCoin going up or down. 

## Features
- Pulls historical market data from Polymarket Gamma API
- Trains XGBoost/scikit-learn models on resolved markets
- Backtests prediction accuracy
- (Phase 3) Live trading via CLOB API

## Setup

### 1. Clone the repo
git clone https://github.com/yourname/polymarket-bot.git
cd polymarket-bot

### 2. Run setup
python3 setup.py

### 3. Add your credentials
cp .env.example .env
# Fill in your values in .env

### 4. Activate environment
source venv/bin/activate  # or just type `polymarket` if you set the alias

## Usage
python3 main.py

## Tech Stack
- Python 3.x
- scikit-learn / XGBoost
- pandas / NumPy
- Polymarket Gamma API
- py-clob-client (Phase 3)

## Disclaimer
This is a personal project. Do not use this to make financial 
decisions. Past prediction accuracy does not guarantee future results.
```

---

**Your project folder structure should look like:**
```
polymarket-bot/
├── venv/               ← never committed
├── .env                ← never committed
├── .env.example        ← committed, no real values
├── .gitignore          ← committed
├── requirements.txt    ← committed
├── README.md           ← committed
├── main.py
├── data/
│   └── .gitkeep        ← empty file so folder shows on GitHub
└── src/
    ├── fetch.py
    ├── model.py
    └── trade.py