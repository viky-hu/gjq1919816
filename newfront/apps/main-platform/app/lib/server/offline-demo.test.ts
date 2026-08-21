import assert from "node:assert/strict";
import test from "node:test";

import {
  getDefaultChatHistoryStorageMode,
  shouldUseOfflineBackendFallback,
} from "./offline-demo.ts";

test("defaults chat history to mock storage for frontend-only demos", () => {
  assert.equal(getDefaultChatHistoryStorageMode(undefined), "mock");
  assert.equal(getDefaultChatHistoryStorageMode(""), "mock");
  assert.equal(getDefaultChatHistoryStorageMode("auto"), "auto");
  assert.equal(getDefaultChatHistoryStorageMode("prisma"), "prisma");
});

test("uses offline backend fallback when service URLs are missing", () => {
  assert.equal(shouldUseOfflineBackendFallback(undefined), true);
  assert.equal(shouldUseOfflineBackendFallback("   "), true);
  assert.equal(shouldUseOfflineBackendFallback("http://127.0.0.1:8000"), false);
});
