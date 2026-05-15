"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  DistributionSummary,
  FlowSummary,
  MarketResult,
  TradeRow,
  WalletSummary,
} from "@/lib/polymarket";

// The browser receives this shape from app/api/markets/route.ts.
type MarketResponse = {
  markets?: MarketResult[];
  error?: string;
};

// The browser receives this shape from app/api/trades/route.ts.
type TradeResponse = {
  trades?: TradeRow[];
  summary?: FlowSummary;
  wallets?: WalletSummary[];
  distributions?: DistributionSummary[];
  error?: string;
};

// Used before the first trade response arrives and after empty/error responses.
const emptySummary: FlowSummary = {
  tradeCount: 0,
  walletCount: 0,
  totalValue: 0,
  buyValue: 0,
  sellValue: 0,
  buyShare: 0,
  netPressure: 0,
  averagePrice: null,
  medianSize: null,
  largestTrade: null,
  latestTrade: null,
};

/**
 * Main dashboard component.
 *
 * Responsibilities:
 * - Search Polymarket markets.
 * - Track the selected market.
 * - Poll recent trades for that market.
 * - Render flow metrics, wallet aggregates, and simple distributions.
 */
export default function Home() {
  // Sidebar/search state.
  const [query, setQuery] = useState("bitcoin");
  const [activeOnly, setActiveOnly] = useState(true);
  const [markets, setMarkets] = useState<MarketResult[]>([]);
  const [selectedConditionId, setSelectedConditionId] = useState("");

  // Trade-flow data returned from /api/trades.
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [summary, setSummary] = useState<FlowSummary>(emptySummary);
  const [wallets, setWallets] = useState<WalletSummary[]>([]);
  const [distributions, setDistributions] = useState<DistributionSummary[]>([]);

  // Loading and error state stays local because this is currently a single page.
  const [marketError, setMarketError] = useState("");
  const [tradeError, setTradeError] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingTrades, setIsLoadingTrades] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Keep selection stable across searches, but fall back to the first result.
  const selectedMarket = useMemo(
    () => markets.find((market) => market.conditionId === selectedConditionId) ?? markets[0],
    [markets, selectedConditionId],
  );

  // Fetch market candidates from the local Next API route.
  const search = useCallback(async () => {
    setIsSearching(true);
    setMarketError("");
    try {
      const response = await fetch(
        `/api/markets?q=${encodeURIComponent(query)}&limit=20&activeOnly=${activeOnly}`,
      );
      const payload = (await response.json()) as MarketResponse;
      if (!response.ok) throw new Error(payload.error ?? "Market search failed");
      const nextMarkets = payload.markets ?? [];
      setMarkets(nextMarkets);
      setSelectedConditionId((current) =>
        nextMarkets.some((market) => market.conditionId === current)
          ? current
          : nextMarkets[0]?.conditionId ?? "",
      );
    } catch (error) {
      setMarketError(error instanceof Error ? error.message : "Market search failed");
    } finally {
      setIsSearching(false);
    }
  }, [activeOnly, query]);

  // Fetch the latest public trades plus server-side aggregates for one market.
  const loadTrades = useCallback(async () => {
    if (!selectedMarket?.conditionId) return;
    setIsLoadingTrades(true);
    setTradeError("");
    try {
      const response = await fetch(`/api/trades?conditionId=${selectedMarket.conditionId}&limit=500`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as TradeResponse;
      if (!response.ok) throw new Error(payload.error ?? "Trade fetch failed");
      setTrades(payload.trades ?? []);
      setSummary(payload.summary ?? emptySummary);
      setWallets(payload.wallets ?? []);
      setDistributions(payload.distributions ?? []);
    } catch (error) {
      setTradeError(error instanceof Error ? error.message : "Trade fetch failed");
    } finally {
      setIsLoadingTrades(false);
    }
  }, [selectedMarket?.conditionId]);

  // Run a market search on first render and whenever search inputs change.
  useEffect(() => {
    void search();
  }, [search]);

  // Load trade data when the selected market changes.
  useEffect(() => {
    void loadTrades();
  }, [loadTrades]);

  // Poll trades every 10 seconds when auto-refresh is enabled.
  useEffect(() => {
    if (!autoRefresh) return;
    const timer = window.setInterval(() => {
      void loadTrades();
    }, 10_000);
    return () => window.clearInterval(timer);
  }, [autoRefresh, loadTrades]);

  // This client-side read is intentionally simple until wallet history exists.
  const shadow = useMemo(() => buildShadowSignal(wallets, summary), [summary, wallets]);

  return (
    <main className="shell">
      <aside className="sidebar">
        <div>
          <p className="eyebrow">Polymarket</p>
          <h1>Trade-Flow Analyzer</h1>
        </div>

        <label className="field">
          <span>Market search</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="bitcoin, election, fed..." />
        </label>

        <label className="check">
          <input type="checkbox" checked={activeOnly} onChange={(event) => setActiveOnly(event.target.checked)} />
          <span>Active markets only</span>
        </label>

        <button className="primary" onClick={() => void search()} disabled={isSearching}>
          {isSearching ? "Searching..." : "Search markets"}
        </button>

        <button className="secondary" onClick={() => void loadTrades()} disabled={!selectedMarket || isLoadingTrades}>
          {isLoadingTrades ? "Refreshing..." : "Refresh trades"}
        </button>

        <label className="check">
          <input type="checkbox" checked={autoRefresh} onChange={(event) => setAutoRefresh(event.target.checked)} />
          <span>Auto-refresh trades</span>
        </label>

        {marketError ? <p className="error">{marketError}</p> : null}

        <div className="market-list">
          {markets.map((market) => (
            <button
              className={market.conditionId === selectedMarket?.conditionId ? "market-item active" : "market-item"}
              key={market.conditionId}
              onClick={() => setSelectedConditionId(market.conditionId)}
            >
              <span>{market.title}</span>
              <small>{formatMoney(market.volume)} volume</small>
            </button>
          ))}
        </div>
      </aside>

      <section className="content">
        {selectedMarket ? (
          <>
            <section className="market-header">
              <div>
                <p className="eyebrow">Selected market</p>
                <h2>{selectedMarket.title}</h2>
                <p className="muted">{selectedMarket.question}</p>
              </div>
              {selectedMarket.url ? (
                <a className="external" href={selectedMarket.url} target="_blank" rel="noreferrer">
                  Open Polymarket
                </a>
              ) : null}
            </section>

            <section className="metrics-grid">
              <Metric label="Trades" value={summary.tradeCount.toLocaleString()} />
              <Metric label="Wallets" value={summary.walletCount.toLocaleString()} />
              <Metric label="Total value" value={formatMoney(summary.totalValue)} />
              <Metric label="Buy share" value={formatPercent(summary.buyShare)} />
              <Metric label="Net pressure" value={formatMoney(summary.netPressure)} accent={summary.netPressure >= 0 ? "good" : "warn"} />
              <Metric label="Largest trade" value={formatMoney(summary.largestTrade)} />
            </section>

            <section className="signal-row">
              <div>
                <p className="eyebrow">Shadow read</p>
                <h3>{shadow.action}</h3>
                <p className="muted">{shadow.reason}</p>
              </div>
              <div className={`confidence ${shadow.confidence}`}>{shadow.confidence}</div>
            </section>

            {tradeError ? <p className="error">{tradeError}</p> : null}

            <section className="two-column">
              <Panel title="Live Trade Tape">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Time</th>
                        <th>Wallet</th>
                        <th>Side</th>
                        <th>Outcome</th>
                        <th>Price</th>
                        <th>Size</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.slice(0, 80).map((trade, index) => (
                        <tr key={`${trade.transactionHash ?? trade.id ?? trade.timestamp}-${index}`}>
                          <td>{formatTime(trade.timestamp)}</td>
                          <td className="mono">{trade.walletHash}</td>
                          <td>
                            <span className={trade.side === "BUY" ? "pill buy" : "pill sell"}>{trade.side || "N A"}</span>
                          </td>
                          <td>{trade.outcome || "N A"}</td>
                          <td>{trade.price.toFixed(3)}</td>
                          <td>{trade.size.toFixed(2)}</td>
                          <td>{formatMoney(trade.tradeValue)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>

              <Panel title="Wallet Leaderboard">
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Wallet</th>
                        <th>Trades</th>
                        <th>Value</th>
                        <th>Pressure</th>
                        <th>Avg Price</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wallets.slice(0, 25).map((wallet) => (
                        <tr key={wallet.walletHash}>
                          <td className="mono">{wallet.walletHash}</td>
                          <td>{wallet.trades}</td>
                          <td>{formatMoney(wallet.totalValue)}</td>
                          <td className={wallet.netPressure >= 0 ? "good-text" : "warn-text"}>{formatMoney(wallet.netPressure)}</td>
                          <td>{wallet.averagePrice.toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </section>

            <section className="two-column bottom">
              <Panel title="Outcome Flow">
                <BarList rows={outcomeBars(trades)} />
              </Panel>
              <Panel title="Distribution Stats">
                <div className="dist-grid">
                  {distributions.map((dist) => (
                    <div className="dist-card" key={dist.metric}>
                      <span>{dist.metric}</span>
                      <strong>{dist.metric === "price" ? dist.mean.toFixed(3) : formatMoney(dist.mean)}</strong>
                      <small>
                        p10 {dist.p10.toFixed(3)} / p50 {dist.p50.toFixed(3)} / p90 {dist.p90.toFixed(3)}
                      </small>
                    </div>
                  ))}
                </div>
              </Panel>
            </section>
          </>
        ) : (
          <section className="empty">
            <h2>Search for a market to begin.</h2>
            <p className="muted">The analyzer will show current trade flow, active wallets, and behavior distributions.</p>
          </section>
        )}
      </section>
    </main>
  );
}

/** Render one dashboard KPI tile. */
function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: string;
  accent?: "good" | "warn";
}) {
  return (
    <div className={`metric ${accent ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

/** Shared bordered panel wrapper for tables and charts. */
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="panel">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

/** Render a small proportional bar chart without adding a charting library. */
function BarList({ rows }: { rows: { label: string; value: number }[] }) {
  const max = Math.max(...rows.map((row) => row.value), 1);
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <span>{row.label}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(row.value / max) * 100}%` }} />
          </div>
          <strong>{formatMoney(row.value)}</strong>
        </div>
      ))}
    </div>
  );
}

/** Aggregate trade value by outcome for the Outcome Flow panel. */
function outcomeBars(trades: TradeRow[]) {
  const totals = new Map<string, number>();
  for (const trade of trades) {
    const label = trade.outcome || "Unknown";
    totals.set(label, (totals.get(label) ?? 0) + trade.tradeValue);
  }
  return [...totals.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((left, right) => right.value - left.value)
    .slice(0, 8);
}

/**
 * Produce a cautious "shadow watch" read.
 *
 * This is not a prediction model yet. It only asks whether the largest wallets
 * dominate recent value and whether their aggregate pressure is positive or
 * negative. Future versions should use wallet history and backtests.
 */
function buildShadowSignal(wallets: WalletSummary[], summary: FlowSummary) {
  const top = wallets.slice(0, 5);
  if (!top.length) {
    return { action: "WATCH", confidence: "low", reason: "No recent wallet flow has been detected yet." };
  }
  const concentratedValue = top.reduce((total, wallet) => total + wallet.totalValue, 0);
  const concentration = summary.totalValue ? concentratedValue / summary.totalValue : 0;
  const direction = summary.netPressure >= 0 ? "positive" : "negative";
  const confidence = concentration > 0.6 ? "high" : concentration > 0.35 ? "medium" : "low";
  return {
    action: "SHADOW WATCH",
    confidence,
    reason: `Top wallets represent ${formatPercent(concentration)} of recent value with ${direction} pressure.`,
  };
}

/** Format numeric values as compact USD strings for dashboard display. */
function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N A";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Math.abs(value) >= 1000 ? 0 : 2,
  }).format(value);
}

/** Format decimals as percentages for buy share and concentration. */
function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "N A";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

/** Format ISO timestamps into local time for the trade tape. */
function formatTime(value: string | null): string {
  if (!value) return "N A";
  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
