import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

const loginSource = readFileSync(new URL("./LoginIntroWindow.tsx", import.meta.url), "utf8");
const loginStyles = readFileSync(new URL("../../styles/window-1-login.css", import.meta.url), "utf8");

test("login loading modules and completion handoff are wired", () => {
  assert.equal(existsSync(new URL("./LoginSplitLoadingTip.tsx", import.meta.url)), true);
  assert.equal(existsSync(new URL("./login-loading-session.ts", import.meta.url)), true);
  assert.equal(existsSync(new URL("./login-loading-tip-sequence.ts", import.meta.url)), true);
  assert.match(loginSource, /onLoadingComplete\?: \(\) => void/);
  assert.match(loginSource, /LoginSplitLoadingTip/);
  assert.match(loginSource, /onLoadingCompleteRef/);
  assert.match(loginSource, /data-loading-state/);
});

test("loading overlay uses the nine-cell source structure and white colors", () => {
  assert.match(loginSource, /LOADING_CELL_PATTERN/);
  assert.match(loginSource, /login-loading-cell/);
  assert.equal((loginSource.match(/login-loading-cell/g) ?? []).length >= 2, true);
  assert.match(loginStyles, /\.login-agent-loading-overlay/);
  assert.match(loginStyles, /\.login-loading-cell/);
  assert.match(loginStyles, /rgba\(255,\s*255,\s*255/);
  assert.match(loginStyles, /@keyframes login-loading-ripple/);
});

test("split presenter does not render raw React text or revert on update", () => {
  const splitSource = readFileSync(new URL("./LoginSplitLoadingTip.tsx", import.meta.url), "utf8");

  assert.match(splitSource, /import \{ SplitText \} from "gsap\/SplitText"/);
  assert.match(splitSource, /type: "chars"/);
  assert.match(splitSource, /preparedTextRef/);
  assert.match(splitSource, /splitRef/);
  assert.match(splitSource, /phase:.*"enter".*"hold".*"exit"/s);
  assert.doesNotMatch(splitSource, />\s*\{text\}\s*<\/div>/);
  assert.doesNotMatch(splitSource, /revertOnUpdate/);
});
