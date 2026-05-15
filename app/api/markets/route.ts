import { NextResponse } from "next/server";
import { searchMarkets } from "@/lib/polymarket";

/**
 * GET /api/markets
 *
 * Query params:
 * - q: market search text
 * - limit: number of markets to return, clamped for safety
 * - activeOnly: defaults to true; pass false to include closed markets
 */
export async function GET(request: Request) {
  // Parse URL query params from the incoming request.
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q") ?? "bitcoin";
  const limit = clamp(Number(searchParams.get("limit") ?? 20), 5, 50);
  const activeOnly = searchParams.get("activeOnly") !== "false";

  try {
    // Delegate all external API work and normalization to lib/polymarket.ts.
    const markets = await searchMarkets(query, limit, activeOnly);
    return NextResponse.json({ markets });
  } catch (error) {
    // Keep client errors JSON-shaped so the UI can show a useful message.
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Market search failed" },
      { status: 502 },
    );
  }
}

/** Bound user-provided numeric query params before calling external APIs. */
function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}
