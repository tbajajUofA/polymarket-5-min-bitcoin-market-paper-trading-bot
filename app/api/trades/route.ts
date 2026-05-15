import { NextResponse } from "next/server";
import {
  buildWallets,
  distributionStats,
  fetchTrades,
  summarizeTrades,
} from "@/lib/polymarket";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const conditionId = searchParams.get("conditionId") ?? "";
  const limit = clamp(Number(searchParams.get("limit") ?? 400), 50, 1000);

  if (!conditionId) {
    return NextResponse.json({ error: "conditionId is required" }, { status: 400 });
  }

  try {
    const trades = await fetchTrades(conditionId, limit);
    const summary = summarizeTrades(trades);
    const wallets = buildWallets(trades);
    const distributions = distributionStats(trades);
    return NextResponse.json({ trades, summary, wallets, distributions });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Trade fetch failed" },
      { status: 502 },
    );
  }
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}
