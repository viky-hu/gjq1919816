import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const requestId = request.headers.get("x-request-id") || randomUUID();
  const account = request.nextUrl.searchParams.get("account")?.trim() ?? "";
  const targetNodes = request.nextUrl.searchParams.get("targetNodes")?.trim() ?? "300";

  const miaRagUrl = process.env.MIA_RAG_NODE_URL?.trim();
  if (!miaRagUrl) {
    return NextResponse.json(
      {
        error: {
          code: "MIA_RAG_NOT_CONFIGURED",
          message: "MiA-RAG backend not configured",
          requestId,
        },
      },
      { status: 503 },
    );
  }

  const internalToken = process.env.FEDERATION_INTERNAL_TOKEN?.trim() ?? "";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30_000);

  try {
    const params = new URLSearchParams();
    if (account) params.set("account", account);
    params.set("targetNodes", targetNodes);

    const res = await fetch(`${miaRagUrl}/api/graph?${params.toString()}`, {
      method: "GET",
      headers: {
        ...(internalToken ? { "X-Federation-Token": internalToken } : {}),
      },
      signal: controller.signal,
      cache: "no-store",
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const errorBody = await res.text().catch(() => "");
      return NextResponse.json(
        {
          error: {
            code: "MIA_RAG_UPSTREAM_ERROR",
            message: `MiA-RAG graph API error (HTTP ${res.status})`,
            detail: errorBody.slice(0, 500),
            requestId,
          },
        },
        { status: 502 },
      );
    }

    const data = await res.json();
    return NextResponse.json(data, { status: 200 });
  } catch (err) {
    clearTimeout(timeout);
    const isTimeout = err instanceof Error && err.name === "AbortError";
    return NextResponse.json(
      {
        error: {
          code: isTimeout ? "MIA_RAG_TIMEOUT" : "MIA_RAG_UNREACHABLE",
          message: isTimeout ? "Graph API timeout" : "Graph API unreachable",
          requestId,
        },
      },
      { status: isTimeout ? 504 : 502 },
    );
  }
}
