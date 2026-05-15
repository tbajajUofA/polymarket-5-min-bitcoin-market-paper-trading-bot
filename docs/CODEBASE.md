# Codebase Documentation

This document explains the active project files after the cleanup from the old
Streamlit/BTC paper-trading prototype to the current Next.js Polymarket
trade-flow analyzer.

## External APIs

- Polymarket Market Data overview: <https://docs.polymarket.com/market-data/overview>
- Gamma market discovery API used by `lib/polymarket.ts`: <https://gamma-api.polymarket.com/events> and <https://gamma-api.polymarket.com/markets>
- Polymarket Data API trades endpoint used by `lib/polymarket.ts`: <https://docs.polymarket.com/api-reference/core/get-trades-for-a-user-or-markets>
- Runtime endpoint called by the app: <https://data-api.polymarket.com/trades>

The Polymarket docs describe Gamma as the public market/event discovery API and
the Data API as the public source for trades, positions, and analytics. This
app only reads public market and trade data.

## Active File Map

### `package.json`

Lines 1-4 define the npm package metadata and mark the app private so npm does
not publish it accidentally.

Lines 5-11 define scripts. Each script calls the local tool through `node`
instead of relying on `node_modules/.bin` executable bits, which avoids the WSL
`next: Permission denied` issue.

Lines 12-16 define runtime dependencies: Next.js, React, and React DOM.

Lines 17-22 define development dependencies: Node/React types and TypeScript.

### `package-lock.json`

This is npm's exact dependency lockfile. Commit it so teammates and deployments
install the same package versions.

### `app/layout.tsx`

Line 1 imports Next's `Metadata` type.

Line 2 imports global CSS for the entire app.

Lines 4-7 define browser/app metadata: title and description.

Lines 9-19 define `RootLayout`, the required App Router wrapper. It renders the
HTML shell and places every route inside `<body>{children}</body>`.

### `app/page.tsx`

Line 1 marks the file as a client component because it uses React state,
effects, and browser polling.

Lines 3-10 import React hooks and shared TypeScript types from
`lib/polymarket.ts`.

Lines 12-23 define response shapes expected from the local API routes.

Lines 25-37 define `emptySummary`, the fallback market-flow metrics before
trades load or when an API call fails.

Lines 39-52 initialize UI state in `Home`: search query, active-only toggle,
market list, selected condition ID, trade rows, summaries, wallet rows,
distribution rows, loading flags, errors, and auto-refresh.

Lines 54-57 compute `selectedMarket`. It keeps the selected market if possible
and falls back to the first search result.

Lines 59-80 define `search`. It calls `/api/markets`, handles errors, stores
market results, and preserves or resets the selected market.

Lines 82-101 define `loadTrades`. It calls `/api/trades`, then stores the trade
tape, summary, wallet leaderboard, and distribution statistics.

Lines 103-109 run the initial market search and load trades when dependencies
change.

Lines 111-117 implement 10-second trade auto-refresh while the toggle is on.

Line 119 computes the local "shadow read" from wallet concentration and net
pressure.

Lines 121-166 render the sidebar: title, market search input, active-market
toggle, search button, refresh button, auto-refresh toggle, errors, and market
result list.

Lines 168-182 render the selected market header and external Polymarket link.

Lines 184-191 render top-level flow metrics: trades, wallets, total value, buy
share, net pressure, and largest trade.

Lines 193-200 render the shadow-read callout.

Line 202 renders trade-fetch errors.

Lines 204-236 render the live trade tape table. It displays time, hashed wallet,
side, outcome, price, size, and value for the latest rows.

Lines 238-264 render the wallet leaderboard table. It aggregates wallets by
value, pressure, trade count, and average price.

Lines 266-283 render lower analytics panels: outcome-flow bars and distribution
cards.

Lines 285-290 render the empty state when no market is selected.

Lines 296-311 define `Metric`, a reusable metric tile component.

Lines 313-320 define `Panel`, a reusable dashboard panel wrapper.

Lines 322-337 define `BarList`, which renders proportional horizontal bars.

Lines 339-349 define `outcomeBars`, which aggregates trade value by outcome.

Lines 351-365 define `buildShadowSignal`. It estimates whether the top wallets
dominate recent value and labels the read as low, medium, or high confidence.

Lines 367-374 define `formatMoney` for USD-ish display.

Lines 376-382 define `formatPercent` for percentage display.

Lines 384-391 define `formatTime` for compact local trade timestamps.

### `app/api/markets/route.ts`

Lines 1-2 import Next's JSON response helper and the market-search function.

Lines 4-19 define the `GET` handler for `/api/markets`. It reads `q`, `limit`,
and `activeOnly` query parameters, calls Polymarket search helpers, and returns
either `{ markets }` or a `502` JSON error.

Lines 21-24 define `clamp`, which protects the external API from unreasonable
limits by bounding search result counts.

### `app/api/trades/route.ts`

Lines 1-7 import Next's response helper and trade analytics helpers.

Lines 9-30 define the `GET` handler for `/api/trades`. It requires
`conditionId`, clamps `limit`, fetches trades, computes summary metrics,
aggregates wallets, computes distributions, and returns all four outputs as
JSON.

Lines 14-16 return a `400` error when `conditionId` is missing.

Lines 24-28 return a `502` JSON error if Polymarket trade fetching or analytics
throws.

Lines 32-35 define `clamp`, bounding trade fetch size to 50-1000.

### `lib/polymarket.ts`

Lines 1-16 define `MarketResult`, the normalized market shape consumed by the
UI.

Lines 18-31 define `TradeRow`, the normalized trade shape consumed by the UI.

Lines 33-45 define `FlowSummary`, the top-level trade-flow metrics.

Lines 47-58 define `WalletSummary`, the per-wallet aggregate row.

Lines 60-68 define `DistributionSummary`, the stats row for price, size, and
trade value.

Lines 70-71 define the external API bases: Gamma for market discovery and Data
API for public trades.

Lines 73-85 define `asItems`, which accepts several possible Polymarket
response envelopes and returns an array of objects.

Lines 87-121 define small type-conversion helpers: `isRecord`, `stringValue`,
`booleanValue`, `numberValue`, `idValue`, and `parseList`.

Lines 123-131 define `priceMap`, which maps Gamma's `outcomes` and
`outcomePrices` arrays into `{ outcomeName: price }`.

Lines 133-158 define `normalizeMarket`, which converts Gamma event/market
payloads into `MarketResult`.

Lines 160-197 define `searchMarkets`. It queries both Gamma `/events` and
`/markets`, deduplicates by condition ID, ranks local matches, and returns the
requested result count.

Lines 199-220 define `fetchGammaItems`, the low-level Gamma fetch helper used by
`searchMarkets`.

Lines 222-245 define `rankMarkets` and `marketSearchScore`, which make searches
like `bitcoin` and `btc` return relevant markets even when upstream search is
loose.

Lines 247-259 define `fetchTrades`. It calls the Polymarket Data API
`/trades`, disables caching, and normalizes rows.

Lines 261-285 define `normalizeTrade`. It computes wallet hash, trade value,
and signed pressure. BUY Yes and SELL No are positive pressure; SELL Yes and BUY
No are negative pressure.

Lines 287-299 define `normalizeTimestamp`, supporting seconds, milliseconds,
and ISO-like strings.

Lines 301-309 define `hashWallet`, a short non-cryptographic display hash that
keeps full wallet addresses out of the UI.

Lines 311-350 define `summarizeTrades`, producing aggregate flow metrics from
normalized trades.

Lines 352-381 define `buildWallets`, grouping trades by wallet hash and sorting
wallets by traded value.

Lines 383-389 define `distributionStats`, generating stats for price, size, and
trade value.

Lines 391-405 define `stat`, which computes mean, standard deviation, p10, p50,
p90, and max for one numeric series.

Lines 407-424 define numeric helpers: `sum`, `mean`, and `percentile`.

### `app/globals.css`

Lines 1-14 define the color system, text colors, alert colors, and shared
shadow.

Lines 16-38 reset layout sizing and default fonts/cursors.

Lines 40-57 define the two-column app shell and fixed sidebar.

Lines 59-91 define heading and eyebrow typography.

Lines 93-157 style the sidebar form controls and buttons.

Lines 159-192 style selectable market result rows.

Lines 194-218 style the main content area and selected-market header.

Lines 220-254 style the metric grid and positive/negative metric colors.

Lines 256-291 style the shadow-signal row and confidence badges.

Lines 293-313 define dashboard panel grids and table scroll containers.

Lines 315-360 style tables, sticky headers, monospace wallet hashes, and
BUY/SELL pills.

Lines 362-396 style horizontal bar charts.

Lines 398-422 style distribution cards.

Lines 424-434 style error and empty states.

Lines 436-478 define responsive behavior for tablet and mobile widths.

### `next.config.ts`

Line 1 imports the Next config type.

Lines 3-5 disable the `x-powered-by` header.

Line 7 exports the config.

### `tsconfig.json`

Lines 1-31 define TypeScript compiler behavior for the Next app: strict mode,
bundler module resolution, React JSX, path alias `@/*`, and the Next plugin.

Lines 32-38 define source files and generated Next type files included by the
main Next build.

Lines 39-42 exclude dependency and virtual-environment folders.

### `tsconfig.typecheck.json`

Lines 1-2 extend the main TypeScript config.

Lines 3-8 restrict standalone `npm run typecheck` to source files.

Lines 9-13 exclude generated output so stale `.next` route types do not break
local source checks.

### `next-env.d.ts`

Lines 1-3 are Next-generated TypeScript references. Keep this file committed.

Lines 5-6 are Next's warning not to manually edit the file.

### `.gitignore`

This file ignores local environment files, Python caches, generated data/model
artifacts, Node dependencies, Next build output, and TypeScript build info. The
important Next additions are `node_modules/`, `.next/`, `out/`, and
`*.tsbuildinfo`.

### `README.md`

The README gives the project overview, explains the current app files, shows how
to run the dashboard, and records the product direction.

### `LICENSE`

The license file defines how the project can be reused. It is not executable
code, but it should stay in the repo.

## Removed Files

The following tracked files were removed because they belonged to the old
Python/Streamlit BTC paper-trading bot and are not used by the active Next.js
analyzer:

- `config.yaml`
- `requirements.txt`
- `src/collector.py`
- `src/data_fetch.py`
- `src/features.py`
- `src/fetch.py`
- `src/load_config.py`
- `src/market_analyzer.py`
- `src/model_runtime.py`
- `src/polymarket_data.py`
- `src/predict.py`
- `src/trader_signals.py`
- `src/trading.py`
- `src/train.py`

If Python/FastAPI workers come back later, they should be rebuilt around the
new analyzer data model rather than carrying forward the BTC-specific bot code.
