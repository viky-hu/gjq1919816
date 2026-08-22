"use client";

import { useLayoutEffect, useRef } from "react";
import { gsap } from "gsap";
import { SplitText } from "gsap/SplitText";

gsap.registerPlugin(SplitText);

export type LoginSplitLoadingTipPhase = "enter" | "hold" | "exit";

type LoginSplitLoadingTipProps = {
  text: string;
  active: boolean;
  phase: "enter" | "hold" | "exit";
  onExitComplete?: () => void;
};

export function LoginSplitLoadingTip({ text, active, phase, onExitComplete }: LoginSplitLoadingTipProps) {
  const rootRef = useRef<HTMLParagraphElement>(null);
  const preparedTextRef = useRef("");
  const splitRef = useRef<SplitText | null>(null);
  const motionRef = useRef<gsap.core.Timeline | null>(null);
  const exitCompletionRef = useRef(false);
  const onExitCompleteRef = useRef(onExitComplete);
  onExitCompleteRef.current = onExitComplete;

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root || !active) return;
    let disposed = false;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    preparedTextRef.current = text;
    root.textContent = text;
    root.setAttribute("aria-label", text);
    root.style.opacity = "0";

    const split = SplitText.create(root, {
      type: "chars",
      charsClass: "login-agent-loading-char",
      aria: "auto",
      reduceWhiteSpace: false,
      smartWrap: true,
      tag: "span",
    });
    splitRef.current = split;
    const chars = split.chars;
    gsap.set(chars, { autoAlpha: reduceMotion ? 1 : 0, y: reduceMotion ? 0 : 18 });
    gsap.set(root, { autoAlpha: reduceMotion ? 1 : 0 });
    exitCompletionRef.current = false;

    return () => {
      disposed = true;
      motionRef.current?.kill();
      motionRef.current = null;
      split.revert();
      splitRef.current = null;
      if (root) root.textContent = "";
    };
  }, [active, text]);

  useLayoutEffect(() => {
    const root = rootRef.current;
    const split = splitRef.current;
    if (!root || !split || !active || preparedTextRef.current !== text) return;
    const chars = split.chars;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    motionRef.current?.kill();
    if (phase === "enter") {
      exitCompletionRef.current = false;
      if (reduceMotion) {
        gsap.set(chars, { autoAlpha: 1, y: 0 });
        gsap.set(root, { autoAlpha: 1 });
        return;
      }
      motionRef.current = gsap.timeline().to(root, { autoAlpha: 1, duration: 0.08 }).fromTo(
        chars,
        { autoAlpha: 0, y: 18 },
        { autoAlpha: 1, y: 0, duration: 0.28, ease: "power2.out", stagger: { each: 0.018, from: "start" } },
      );
    } else if (phase === "hold") {
      gsap.set(root, { autoAlpha: 1 });
      gsap.set(chars, { autoAlpha: 1, y: 0 });
    } else {
      if (exitCompletionRef.current) return;
      exitCompletionRef.current = true;
      motionRef.current = gsap.timeline({ onComplete: () => {
        onExitCompleteRef.current?.();
      }}).to(root, { autoAlpha: 0, duration: reduceMotion ? 0 : 0.2, ease: "power1.out" });
    }
  }, [active, phase, text]);

  return <p ref={rootRef} className="login-agent-loading-tip" aria-live="polite" />;
}
