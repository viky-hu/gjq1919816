import { LOGIN_LOADING_TIPS, type LoginLoadingTip } from "./login-loading-tips.ts";

export { LOGIN_LOADING_TIPS } from "./login-loading-tips.ts";

export type LoginLoadingTipPresentation = {
  tip: LoginLoadingTip;
  entranceMs: number;
  holdMs: number;
  exitMs: number;
};

export type LoginLoadingSequenceResult =
  | { kind: "tip"; presentation: LoginLoadingTipPresentation }
  | { kind: "complete" };

export const LOGIN_LOADING_TIP_EXIT_MS = 220;

const hashText = (text: string) => {
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
};

const buildPresentation = (tip: LoginLoadingTip): LoginLoadingTipPresentation => {
  const characterCount = Array.from(tip.text).length;
  const entranceMs = Math.min(760, Math.max(420, 280 + characterCount * 16));
  const holdMs = 1250 + (hashText(tip.id) % 280);
  return { tip, entranceMs, holdMs, exitMs: LOGIN_LOADING_TIP_EXIT_MS };
};

export function createLoginLoadingTipSequence(tips: readonly LoginLoadingTip[] = LOGIN_LOADING_TIPS) {
  let index = -1;
  let started = false;

  const startOrAdvance = (): LoginLoadingSequenceResult => {
    if (!started) started = true;
    index += 1;
    if (index >= tips.length) return { kind: "complete" };
    return { kind: "tip", presentation: buildPresentation(tips[index]) };
  };

  return {
    start: startOrAdvance,
    startOrAdvance,
    advanceAfterExit: startOrAdvance,
    get index() {
      return index;
    },
  };
}
