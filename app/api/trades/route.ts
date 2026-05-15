import { NextResponse } from "next/server";
import {
  buildWallets,
  distributionStats,
  fetchTrades,
  summarizeTrades,
} from "@/lib/polymarket";

/**
 * GET /api/trades
 *
 * Query params:
 * - conditionId: required Polymarket market condition id
 * - limit: number of recent trades to inspect, clamped to 50-1000
 */
export async function GET(request: Request) {
  // Pull the selected market id and requested trade count from the URL.
  const { searchParams } = new URL(request.url);
  const conditionId = searchParams.get("conditionId") ?? "";
  const limit = clamp(Number(searchParams.get("limit") ?? 400), 50, 1000);

  // The Polymarket Data API needs a market condition id to fetch trades.
  if (!conditionId) {
    return NextResponse.json({ error: "conditionId is required" }, { status: 400 });
  }

  try {
    // Fetch raw public trades, normalize them, then derive dashboard analytics.
    const trades = await fetchTrades(conditionId, limit);
    const summary = summarizeTrades(trades);
    const wallets = buildWallets(trades);
    const distributions = distributionStats(trades);
    return NextResponse.json({ trades, summary, wallets, distributions });
  } catch (error) {
    // External API failures are returned as 502 because our route is a proxy.
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Trade fetch failed" },
      { status: 502 },
    );
  }
}

/** Bound user-provided numeric query params before calling external APIs. */
function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}
