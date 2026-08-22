import assert from "node:assert/strict";
import test from "node:test";

import { createLoginLoadingSessionController } from "./login-loading-session.ts";

test("loading session accepts one current tip exit after reveal", () => {
  const session = createLoginLoadingSessionController();
  const sessionId = session.begin();

  assert.equal(session.activateTip(sessionId, "tip-1"), true);
  assert.equal(session.markRevealComplete(sessionId, "tip-1"), true);
  assert.equal(session.acceptExit(sessionId, "tip-1"), true);
  assert.equal(session.acceptExit(sessionId, "tip-1"), false);
});

test("loading session rejects stale callbacks after a new session begins", () => {
  const session = createLoginLoadingSessionController();
  const staleId = session.begin();
  session.activateTip(staleId, "tip-1");
  const currentId = session.begin();

  assert.equal(session.markRevealComplete(staleId, "tip-1"), false);
  assert.equal(session.acceptExit(staleId, "tip-1"), false);
  assert.equal(session.activateTip(currentId, "tip-2"), true);
});
