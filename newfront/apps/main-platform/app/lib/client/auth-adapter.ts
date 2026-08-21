/**
 * auth-adapter.ts — 认证接口适配层
 *
 * 配置 NEXT_PUBLIC_MIA_RAG_AUTH_URL 时调用真实 MiA-RAG 后端；
 * 未配置时使用本地演示账号，保证前端可离线预览。
 */
import { resolveDemoLogin, shouldUseDemoAuth } from "./demo-auth";

export interface LoginParams {
  account: string;
  password: string;
}

export interface LoginResult {
  ok: boolean;
  isAdmin: boolean;
  nodeType?: string;  // "center" or "edge"
  errorMessage?: string;
}

export interface RegisterParams {
  account: string;
  password: string;
}

export interface RegisterResult {
  ok: boolean;
  errorMessage?: string;
}

const AUTH_URL = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_MIA_RAG_AUTH_URL?.trim()) || "";

export const MIA_RAG_TOKEN_KEY = "mia_rag_token";

export async function authLogin(params: LoginParams): Promise<LoginResult> {
  if (shouldUseDemoAuth(AUTH_URL)) {
    return resolveDemoLogin(params);
  }

  try {
    const res = await fetch(`${AUTH_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: params.account, password: params.password }),
    });
    if (!res.ok) {
      const data = await res.json() as { detail?: string | Array<{ msg?: string }> };
      const msg = typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((e) => e.msg).filter(Boolean).join("; ")
          : "登录失败";
      return { ok: false, isAdmin: false, errorMessage: msg };
    }
    const data = await res.json() as { access_token: string; user: { role: string; node_type?: string } };
    if (typeof window !== "undefined") {
      localStorage.setItem(MIA_RAG_TOKEN_KEY, data.access_token);
    }
    return { ok: true, isAdmin: data.user.role === "admin", nodeType: data.user.node_type };
  } catch {
    return { ok: false, isAdmin: false, errorMessage: "无法连接认证服务，请确认后端已启动" };
  }
}

export async function authRegister(params: RegisterParams): Promise<RegisterResult> {
  if (shouldUseDemoAuth(AUTH_URL)) {
    void params;
    return { ok: true };
  }

  try {
    const res = await fetch(`${AUTH_URL}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: params.account, password: params.password }),
    });
    if (!res.ok) {
      const data = await res.json() as { detail?: string | Array<{ msg?: string }> };
      const msg = typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((e) => e.msg).filter(Boolean).join("; ")
          : "申请注册失败";
      return { ok: false, errorMessage: msg };
    }
    return { ok: true };
  } catch {
    return { ok: false, errorMessage: "无法连接认证服务，请确认后端已启动" };
  }
}
