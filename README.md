# Polymarket Trade-Flow Analyzer

A Next.js research dashboard for inspecting Polymarket market activity, recent
trades, wallet behavior, and early shadow-signal ideas.

The project has pivoted away from a BTC paper trading bot. The new goal is to
search any Polymarket market, watch who is trading what, study the distributions
active wallets follow, and eventually model whether high-performing wallets can
be identified early enough to shadow.

## Current App

- `app/page.tsx` is the main Next.js dashboard.
- `app/api/markets/route.ts` searches Polymarket Gamma events.
- `app/api/trades/route.ts` fetches recent public trades and returns:
  - trade tape rows
  - market flow summary
  - wallet leaderboard
  - distribution stats
- `lib/polymarket.ts` contains API normalization and analytics helpers.
- `src/` still contains the earlier Python research code, which can be reused
  later for heavier data science, ingestion jobs, and model training.

## Run

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:3000
```

## Product Direction

The core research question is:

```text
Can we identify wallets or wallet clusters with repeatable behavior before
their trades become obvious in market prices?
```

Near-term build path:

1. Add Postgres tables for markets, trades, wallets, wallet snapshots, and model
   runs.
2. Move ingestion into Python/FastAPI workers.
3. Keep Next.js as the product UI.
4. Add wallet history pages and distributions by market category.
5. Backtest shadow signals against latency, slippage, and sample-size bias.

## Target Stack

```text
Next.js + React + TypeScript frontend
Python + FastAPI backend
Postgres database
Python workers for ingestion and modeling
Redis later for queues/pubsub/cache
```

This repo currently starts with the Next.js UI and API routes so the interface
can evolve quickly before the backend is split out.
