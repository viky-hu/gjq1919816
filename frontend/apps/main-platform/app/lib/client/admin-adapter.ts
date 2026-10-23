/**
 * admin-adapter.ts — 管理员数据接口适配层
 *
 * 直接调用真实后端 API（NEXT_PUBLIC_MIA_RAG_AUTH_URL）。
 */

export type NodeType = "普通节点" | "中心节点";

export interface AdminUser {
  account: string;
  nodeName: string;
  fileCount: number;
  nodeType: NodeType;
}

export type RequestType =
  | "注册账号"
  | "更改节点名称"
  | "更改节点位置"
  | "申请成为中心节点"
  | "申请还原为普通节点"
  | "配置法官模型";

export interface AdminRequest {
  id: string;
  account: string;
  requestType: RequestType;
  remark: string;
  createdAt: string;
}

export interface AdminHistory {
  id: string;
  account: string;
  requestType: RequestType;
  remark: string;
  approvedAt: string;
}

export interface ApproveResult {
  ok: boolean;
  errorMessage?: string;
}

const AUTH_URL = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_MIA_RAG_AUTH_URL?.trim()) || "";
const MIA_RAG_TOKEN_KEY = "mia_rag_token";

function getAuthHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = localStorage.getItem(MIA_RAG_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// ── 用户列表 ────────────────────────────────────────────────────

export async function adminListUsers(): Promise<AdminUser[]> {
  if (!AUTH_URL) return [];

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/users`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json() as AdminUser[];
    return data;
  } catch {
    return [];
  }
}

// ── 待审核申请（中心节点申请） ──────────────────────────────────

export async function adminListRequests(): Promise<AdminRequest[]> {
  if (!AUTH_URL) return [];

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/requests`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json() as { id: string; account: string; requestType: string; remark: string; createdAt: string }[];
    return data.map((r) => ({
      id: r.id,
      account: r.account,
      requestType: r.requestType as RequestType,
      remark: r.remark,
      createdAt: r.createdAt,
    }));
  } catch {
    return [];
  }
}

// ── 待审核用户注册 ──────────────────────────────────────────────

export interface AdminPendingUser {
  /** 后端 users.id（审批接口要用） */
  id: number;
  account: string;
  email: string;
  createdAt: string;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value).slice(0, 10);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** 待管理员审批的注册申请（后端 /api/admin/pending-users） */
export async function adminListPendingUsers(): Promise<AdminPendingUser[]> {
  if (!AUTH_URL) return [];

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/pending-users`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json() as Array<{
      id: number;
      username: string;
      email?: string | null;
      created_at?: string | null;
    }>;
    return data.map((u) => ({
      id: u.id,
      account: u.username,
      email: u.email ?? "",
      createdAt: formatDate(u.created_at),
    }));
  } catch {
    return [];
  }
}

/** 通过 / 拒绝注册申请（后端 /api/admin/users/{id}/approve） */
export async function adminApproveUser(
  userId: number,
  approved: boolean,
): Promise<ApproveResult> {
  if (!AUTH_URL) return { ok: false, errorMessage: "后端未配置" };

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/users/${userId}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ approved }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({} as { detail?: string }));
      return { ok: false, errorMessage: data.detail ?? "审核失败" };
    }

    return { ok: true };
  } catch {
    return { ok: false, errorMessage: "网络错误" };
  }
}

// ── 历史记录 ────────────────────────────────────────────────────

export async function adminListHistory(): Promise<AdminHistory[]> {
  if (!AUTH_URL) return [];

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/history`, {
      headers: getAuthHeaders(),
    });
    if (!res.ok) return [];
    const data = await res.json() as { id: string; account: string; requestType: string; remark: string; approvedAt: string }[];
    return data.map((h) => ({
      id: h.id,
      account: h.account,
      requestType: h.requestType as RequestType,
      remark: h.remark,
      approvedAt: h.approvedAt,
    }));
  } catch {
    return [];
  }
}

// ── 提交申请 ────────────────────────────────────────────────────

export async function adminSubmitRequest(
  account: string,
  type: RequestType,
  remark: string,
): Promise<void> {
  if (!AUTH_URL) return;

  await fetch(`${AUTH_URL}/api/admin/requests`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
    },
    body: JSON.stringify({ requestType: type, remark }),
  });
}

// ── 审核通过 ────────────────────────────────────────────────────

export async function adminApproveRequest(requestId: string): Promise<ApproveResult> {
  if (!AUTH_URL) return { ok: false, errorMessage: "后端未配置" };

  try {
    const res = await fetch(`${AUTH_URL}/api/admin/requests/${requestId}/approve`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeaders(),
      },
      body: JSON.stringify({ approved: true }),
    });

    if (!res.ok) {
      const data = await res.json() as { detail?: string };
      return { ok: false, errorMessage: data.detail ?? "审核失败" };
    }

    return { ok: true };
  } catch {
    return { ok: false, errorMessage: "网络错误" };
  }
}
