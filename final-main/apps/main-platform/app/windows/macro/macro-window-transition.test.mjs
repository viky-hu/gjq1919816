import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const read = (path) => readFile(new URL(path, import.meta.url), "utf8");

test("login handoff targets the macro platform and passes its one-shot transition", async () => {
  const source = await read("../../login-window-demo.tsx");
  assert.match(source, /setActiveWindow\("macro"\)/);
  assert.match(source, /<MacroWindow[\s\S]*introTransition=\{macroIntroTransition\}/);
  assert.match(source, /onIntroTransitionComplete=\{[^}]*\}/);
  const handoff = source.match(/const handleLoadingComplete = \(\) => \{([\s\S]*?)\n  \};/);
  assert.ok(handoff, "loading completion handler should remain explicit");
  assert.match(handoff[1], /setActiveWindow\("macro"\)/);
  assert.doesNotMatch(handoff[1], /setActiveWindow\("main"\)/);
  const logout = source.match(/const handleBackToLogin = \(\) => \{([\s\S]*?)\n  \};/);
  assert.ok(logout, "logout handler should remain explicit");
  assert.match(logout[1], /setMacroIntroTransition\("none"\)/);
});

test("leaving the macro platform consumes the transition before navigation", async () => {
  const source = await read("../../login-window-demo.tsx");
  const navigation = source.match(/const handleNavigate = \(nextWindow: ActiveWindow\) => \{([\s\S]*?)\n  \};/);
  assert.ok(navigation, "navigation handler should remain explicit");
  assert.match(navigation[1], /activeWindow === "macro" && nextWindow !== "macro"/);
  assert.ok(
    navigation[1].indexOf('setMacroIntroTransition("none")') < navigation[1].indexOf("setActiveWindow(nextWindow)"),
    "transition should be consumed before active window changes",
  );
  assert.match(source, /const handleIntroTransitionComplete[\s\S]*setMacroIntroTransition\("none"\)/);
});

test("macro intro starts from the center line and never recreates a full blue block", async () => {
  const source = await read("./MacroWindow.tsx");
  const styles = await read("../../styles/window-5-macro.css");
  assert.match(source, /introTransition\?: "from-login-loading" \| "none"/);
  assert.match(source, /macro-window-transition-layer/);
  assert.match(source, /transitionCenter/);
  assert.match(source, /transitionFinal/);
  assert.match(source, /onIntroTransitionComplete\?: \(\) => void/);
  assert.match(source, /onComplete:[\s\S]*setIntroComplete\(true\)[\s\S]*onIntroTransitionComplete/);
  assert.doesNotMatch(source, /transitionFull/);
  assert.match(styles, /\.macro-window-transition-layer/);
  assert.match(styles, /pointer-events:\s*none/);
});
