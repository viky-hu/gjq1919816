import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pagePath = new URL("./page.tsx", import.meta.url);
const globalsPath = new URL("./globals.css", import.meta.url);

test("renders a standalone full-screen SVG canvas on the home page", () => {
  const source = readFileSync(pagePath, "utf8");

  assert.match(source, /<svg[^>]*aria-label="Empty canvas"/);
  assert.match(source, /preserveAspectRatio="none"/);
  assert.doesNotMatch(source, /LoginWindowDemo/);
});

test("uses the canvas color as the document background", () => {
  const source = readFileSync(globalsPath, "utf8");

  assert.match(source, /background-color:\s*#353330/);
});
