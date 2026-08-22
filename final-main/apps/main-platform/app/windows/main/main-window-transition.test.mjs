import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const mainSource = readFileSync(new URL("./MainWindow.tsx", import.meta.url), "utf8");
const mainStyles = readFileSync(new URL("../../styles/window-3-main.css", import.meta.url), "utf8");

test("main window exposes the login loading intro transition", () => {
  assert.match(mainSource, /introTransition\?: "from-login-loading" \| "none"/);
  assert.match(mainSource, /main-window-transition-layer/);
  assert.match(mainSource, /transitionFull/);
  assert.match(mainSource, /transitionCenter/);
  assert.match(mainSource, /transitionFinal/);
  assert.match(mainStyles, /\.main-window-transition-layer/);
});
