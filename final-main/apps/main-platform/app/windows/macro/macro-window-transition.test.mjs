import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("login handoff targets the macro platform and passes its one-shot transition", async () => {
  const source = await read("../../login-window-demo.tsx");
  assert.match(source, /setActiveWindow\("macro"\)/);
  assert.match(source, /<MacroWindow[\s\S]*introTransition=\{macroIntroTransition\}/);
  const handoff = source.match(/const handleLoadingComplete = \(\) => \{([\s\S]*?)\n  \};/);
  assert.ok(handoff, "loading completion handler should remain explicit");
  assert.match(handoff[1], /setActiveWindow\("macro"\)/);
  assert.doesNotMatch(handoff[1], /setActiveWindow\("main"\)/);
});

test("macro intro starts from the center line and never recreates a full blue block", async () => {
  const source = await read("./MacroWindow.tsx");
  const styles = await read("../../styles/window-5-macro.css");
  assert.match(source, /introTransition\?: "from-login-loading" \| "none"/);
  assert.match(source, /macro-window-transition-layer/);
  assert.match(source, /transitionCenter/);
  assert.match(source, /transitionFinal/);
  assert.doesNotMatch(source, /transitionFull/);
  assert.match(styles, /\.macro-window-transition-layer/);
  assert.match(styles, /pointer-events:\s*none/);
});
