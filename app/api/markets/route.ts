import { NextResponse } from "next/server";
import { searchMarkets } from "@/lib/polymarket";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q") ?? "bitcoin";
  const limit = clamp(Number(searchParams.get("limit") ?? 20), 5, 50);
  const activeOnly = searchParams.get("activeOnly") !== "false";

  try {
    const markets = await searchMarkets(query, limit, activeOnly);
    return NextResponse.json({ markets });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Market search failed" },
      { status: 502 },
    );
  }
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}
