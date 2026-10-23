import { NextRequest, NextResponse } from "next/server";
import {
  enforceAccountOwnership,
  requireNodeAuth,
} from "@/app/api/_shared/node-auth";
import { toNodeDatabaseErrorResponse } from "@/app/api/database/error-response";
import { getNodeMetrics } from "@/app/lib/server/node-data";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const requestId = request.headers.get("x-request-id") || "db-metrics-get";
  const authResult = requireNodeAuth(request, requestId);
  if (!authResult.ok) {
    return authResult.response;
  }

  const rawAccount = request.nextUrl.searchParams.get("account")?.trim() ?? "";
  const ownerCheck = enforceAccountOwnership(authResult.context, rawAccount, requestId);
  if (ownerCheck) {
    return ownerCheck;
  }

  try {
    const ownerAccount = authResult.context.account || rawAccount;
    const metrics = await getNodeMetrics(ownerAccount);

    // Also fetch file count from Python backend
    const miaRagUrl = process.env.MIA_RAG_NODE_URL?.trim();
    if (miaRagUrl) {
      try {
        const res = await fetch(`${miaRagUrl}/api/macro/file-count?account=${encodeURIComponent(ownerAccount)}`, {
          signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
          const backend = await res.json() as { total_files?: number; cluster_count?: number };
          if (typeof backend.total_files === "number" && backend.total_files > metrics.totalFiles) {
            metrics.totalFiles = backend.total_files;
          }
          if (typeof backend.cluster_count === "number" && backend.cluster_count > metrics.clusterCount) {
            metrics.clusterCount = backend.cluster_count;
          }
        }
      } catch { /* ignore backend fetch errors */ }
    }

    return NextResponse.json(metrics);
  } catch (error) {
    return toNodeDatabaseErrorResponse(error);
  }
}
