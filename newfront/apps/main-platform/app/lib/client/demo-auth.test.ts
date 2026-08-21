import assert from "node:assert/strict";
import test from "node:test";

import { resolveDemoLogin, shouldUseDemoAuth } from "./demo-auth.ts";

test("uses demo auth when no auth backend URL is configured", () => {
  assert.equal(shouldUseDemoAuth(""), true);
  assert.equal(shouldUseDemoAuth("   "), true);
  assert.equal(shouldUseDemoAuth("https://example.test"), false);
});

test("accepts built-in admin and normal demo accounts", () => {
  assert.deepEqual(resolveDemoLogin({ account: "admin", password: "311311" }), {
    ok: true,
    isAdmin: true,
    nodeType: "center",
  });

  assert.deepEqual(resolveDemoLogin({ account: "user", password: "123456" }), {
    ok: true,
    isAdmin: false,
    nodeType: "edge",
  });
});

test("rejects unknown demo credentials with a readable message", () => {
  assert.deepEqual(resolveDemoLogin({ account: "admin", password: "wrong" }), {
    ok: false,
    isAdmin: false,
    errorMessage: "演示账号或密码不正确",
  });
});
