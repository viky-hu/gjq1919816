import assert from "node:assert/strict";
import test from "node:test";

import {
  createLoginLoadingTipSequence,
} from "./login-loading-tip-sequence.ts";
import { LOGIN_LOADING_TIPS } from "./login-loading-tips.ts";

test("mock loading tips advance in the confirmed order and complete after the final exit", () => {
  const sequence = createLoginLoadingTipSequence();
  const seen = [];

  for (;;) {
    const action = sequence.startOrAdvance();
    if (action.kind === "complete") break;
    seen.push(action.presentation.tip.text);
  }

  assert.deepEqual(seen, LOGIN_LOADING_TIPS.map((tip) => tip.text));
  assert.equal(new Set(seen).size, LOGIN_LOADING_TIPS.length);
});

test("mock loading presentation derives duration from text without a fixed total timer", () => {
  const sequence = createLoginLoadingTipSequence();
  const action = sequence.startOrAdvance();

  assert.equal(action.kind, "tip");
  assert.ok(action.presentation.entranceMs >= 280);
  assert.ok(action.presentation.holdMs >= 1100);
  assert.ok(action.presentation.exitMs >= 180);
  assert.equal("totalDurationMs" in action.presentation, false);
});
