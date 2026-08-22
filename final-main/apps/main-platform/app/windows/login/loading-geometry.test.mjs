import assert from "node:assert/strict";
import test from "node:test";
import {
  FULLSCREEN_COORDS,
  LINE_EXIT_OVERTRAVEL,
  getLineExitCoords,
} from "../shared/coords.ts";
import { shouldUseEmptyLoginPreview } from "./login-preview.ts";

test("loading expansion ends at the full SVG viewport", () => {
  assert.deepEqual(FULLSCREEN_COORDS, {
    x1: 0,
    x2: 1440,
    y1: 0,
    y2: 900,
  });
});

test("loading line tail moves every line fully outside the viewport", () => {
  assert.deepEqual(getLineExitCoords(FULLSCREEN_COORDS), {
    x1: -LINE_EXIT_OVERTRAVEL,
    x2: 1440 + LINE_EXIT_OVERTRAVEL,
    y1: -LINE_EXIT_OVERTRAVEL,
    y2: 900 + LINE_EXIT_OVERTRAVEL,
  });
});

test("empty login preview bypass is limited to an empty form", () => {
  assert.equal(shouldUseEmptyLoginPreview("", ""), true);
  assert.equal(shouldUseEmptyLoginPreview("preview", ""), false);
  assert.equal(shouldUseEmptyLoginPreview("", "preview"), false);
});
