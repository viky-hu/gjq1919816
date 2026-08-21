import type { LoginResult } from "./auth-adapter";

const DEMO_ACCOUNTS: Record<string, { password: string; isAdmin: boolean; nodeType: "center" | "edge" }> = {
  admin: { password: "311311", isAdmin: true, nodeType: "center" },
  user: { password: "123456", isAdmin: false, nodeType: "edge" },
};

export function shouldUseDemoAuth(authUrl: string | undefined | null): boolean {
  return !authUrl?.trim();
}

export function resolveDemoLogin(params: { account: string; password: string }): LoginResult {
  const account = params.account.trim().toLowerCase();
  const demo = DEMO_ACCOUNTS[account];
  if (!demo || demo.password !== params.password) {
    return { ok: false, isAdmin: false, errorMessage: "演示账号或密码不正确" };
  }

  return {
    ok: true,
    isAdmin: demo.isAdmin,
    nodeType: demo.nodeType,
  };
}
