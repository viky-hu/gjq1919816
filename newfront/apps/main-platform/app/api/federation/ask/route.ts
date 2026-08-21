import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { requireNodeAuth, requireRole } from "@/app/api/_shared/node-auth";
import { FederationAskRequestSchema } from "@/app/lib/server/federation/schemas";
import { askCentral } from "@/app/lib/server/federation/central-client";
import { toFederationErrorResponse } from "@/app/lib/server/federation/errors";
import { shouldUseOfflineBackendFallback } from "@/app/lib/server/offline-demo";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest) {
  const requestId = request.headers.get("x-request-id") || randomUUID();
  const authResult = requireNodeAuth(request, requestId);
  if (!authResult.ok) {
    return authResult.response;
  }

  const roleCheck = requireRole(authResult.context, requestId, "central");
  if (roleCheck) {
    return roleCheck;
  }

  try {
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json(
        {
          error: {
            code: "FEDERATION_BAD_JSON",
            message: "请求体必须为 JSON 格式",
            requestId,
          },
        },
        { status: 400 },
      );
    }

    const parsed = FederationAskRequestSchema.safeParse(body);
    if (!parsed.success) {
      const message = parsed.error.issues[0]?.message ?? "参数错误";
      return NextResponse.json(
        {
          error: {
            code: "FEDERATION_BAD_REQUEST",
            message,
            requestId,
          },
        },
        { status: 422 },
      );
    }

    const centralUrl = process.env.FEDERATION_CENTRAL_BASE_URL?.trim();
    const result = shouldUseOfflineBackendFallback(centralUrl)
      ? {
          requestId,
          status: "partial" as const,
          answer: `演示模式已收到中心聚合问题：“${parsed.data.question}”。当前未配置中心服务，以下为本地前端闭环响应。`,
          details: [
            {
              node: authResult.context.account || "本机节点",
              status: "ok",
              confidence: 0.66,
              answer_preview: "本地演示节点已返回可用占位结果",
              detail: "未配置 FEDERATION_CENTRAL_BASE_URL，已跳过真实联邦请求。",
            },
          ],
        }
      : await askCentral(parsed.data.question, requestId);

    console.info("[federation.ask]", {
      requestId,
      account: authResult.context.account,
      status: result.status,
      detailsCount: result.details.length,
    });

    return NextResponse.json(result, { status: 200 });
  } catch (error) {
    const normalized = toFederationErrorResponse(error, requestId);
    console.error("[federation.ask.error]", {
      requestId,
      status: normalized.status,
      code: normalized.body.error.code,
      message: normalized.body.error.message,
    });
    return NextResponse.json(normalized.body, { status: normalized.status });
  }
}
