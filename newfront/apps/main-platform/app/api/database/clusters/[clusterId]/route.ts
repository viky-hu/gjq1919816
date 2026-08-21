import { NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import {
  enforceAccountOwnership,
  requireNodeAuth,
} from "@/app/api/_shared/node-auth";
import { toNodeDatabaseErrorResponse } from "@/app/api/database/error-response";
import { deleteNodeCluster, renameNodeCluster, resolveNodeAccount } from "@/app/lib/server/node-data";

export const dynamic = "force-dynamic";

const DeleteClusterSchema = z.object({
  account: z.string().trim().min(1, "账号不能为空"),
  actor: z.string().trim().max(32, "节点名称不能超过 32 个字符").optional(),
});

const RenameClusterSchema = z.object({
  account: z.string().trim().min(1, "账号不能为空"),
  actor: z.string().trim().max(32, "节点名称不能超过 32 个字符").optional(),
  name: z.string().trim().min(1, "名称不能为空").max(50, "名称不能超过 50 个字符"),
});

// PATCH /api/database/clusters/[clusterId] — rename cluster
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ clusterId: string }> },
) {
  const { clusterId } = await params;
  const requestId = request.headers.get("x-request-id") || "db-cluster-rename";
  const authResult = requireNodeAuth(request, requestId);
  if (!authResult.ok) {
    return authResult.response;
  }

  let body: unknown = {};
  try {
    const raw = await request.text();
    if (raw.trim()) {
      body = JSON.parse(raw) as unknown;
    }
  } catch {
    return NextResponse.json({ error: "请求体必须为 JSON 格式" }, { status: 400 });
  }

  const result = RenameClusterSchema.safeParse(body);
  if (!result.success) {
    const message = result.error.issues[0]?.message ?? "参数错误";
    return NextResponse.json({ error: message }, { status: 422 });
  }

  try {
    const ownerCheck = enforceAccountOwnership(authResult.context, result.data.account, requestId);
    if (ownerCheck) {
      return ownerCheck;
    }

    const requestAccount = authResult.context.account || result.data.account;
    const requestActor = result.data.actor ?? authResult.context.actor;
    const ownerAccount = resolveNodeAccount({
      account: requestAccount,
      actor: requestActor,
    });
    const renamed = await renameNodeCluster({
      account: ownerAccount,
      actor: requestActor,
      clusterId,
      name: result.data.name,
    });
    if (!renamed) {
      return NextResponse.json({ error: "聚类不存在" }, { status: 404 });
    }

    return NextResponse.json({ ok: true, cluster: renamed });
  } catch (error) {
    return toNodeDatabaseErrorResponse(error);
  }
}

// DELETE /api/database/clusters/[clusterId]
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ clusterId: string }> },
) {
  const { clusterId } = await params;
  const requestId = request.headers.get("x-request-id") || "db-cluster-delete";
  const authResult = requireNodeAuth(request, requestId);
  if (!authResult.ok) {
    return authResult.response;
  }

  let body: unknown = {};
  try {
    const raw = await request.text();
    if (raw.trim()) {
      body = JSON.parse(raw) as unknown;
    }
  } catch {
    return NextResponse.json({ error: "请求体必须为 JSON 格式" }, { status: 400 });
  }

  const result = DeleteClusterSchema.safeParse(body);
  if (!result.success) {
    const message = result.error.issues[0]?.message ?? "参数错误";
    return NextResponse.json({ error: message }, { status: 422 });
  }

  try {
    const ownerCheck = enforceAccountOwnership(authResult.context, result.data.account, requestId);
    if (ownerCheck) {
      return ownerCheck;
    }

    const requestAccount = authResult.context.account || result.data.account;
    const requestActor = result.data.actor ?? authResult.context.actor;
    const ownerAccount = resolveNodeAccount({
      account: requestAccount,
      actor: requestActor,
    });
    const deleted = await deleteNodeCluster({
      account: ownerAccount,
      actor: requestActor,
      clusterId,
    });
    if (!deleted) {
      return NextResponse.json({ error: "聚类不存在" }, { status: 404 });
    }

    return NextResponse.json({ ok: true });
  } catch (error) {
    return toNodeDatabaseErrorResponse(error);
  }
}
