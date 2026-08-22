"use client";

import { useLayoutEffect, useRef, useState, useCallback } from "react";
import { gsap } from "gsap";
import { DotGrid } from "./components/DotGrid";
import { ChatCanvasLines } from "./components/ChatCanvasLines";
import { ChatInteractionPanel } from "./components/ChatInteractionPanel";
import { TraceWindow, type TraceEvidence } from "./components/TraceWindow";
import { GlobalTopNav } from "../shared/GlobalTopNav";
import { useAppRuntime } from "@/app/components/runtime/AppRuntimeProvider";

type ChatMode = "local" | "global";

interface MainWindowProps {
  onBack?: () => void;
  onOpenDatabase?: () => void;
  onOpenMacro?: () => void;
  introTransition?: "from-login-loading" | "none";
}

export function MainWindow({ onBack, onOpenDatabase, onOpenMacro, introTransition = "none" }: MainWindowProps) {
  const { modelConfigState, setModelConfigState, isSelfCenterNode } = useAppRuntime();
  const [canvasReady, setCanvasReady] = useState(false);
  const [traceTarget, setTraceTarget] = useState<{ msgId: string; evidence: TraceEvidence[] } | null>(null);
  const [chatMode, setChatMode] = useState<ChatMode>("local");
  const transitionSvgRef = useRef<SVGSVGElement>(null);
  const transitionRectRef = useRef<SVGRectElement>(null);
  const [introComplete, setIntroComplete] = useState(introTransition !== "from-login-loading");

  useLayoutEffect(() => {
    if (introTransition !== "from-login-loading") {
      setIntroComplete(true);
      return;
    }
    const rect = transitionRectRef.current;
    if (!rect) return;
    let disposed = false;
    const measure = () => ({ width: Math.max(window.innerWidth, 1), height: Math.max(window.innerHeight, 1) });
    const navHeight = 50;
    const lineHeight = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 3 : 2;
    const transitionFull = { x: 0, y: 0, width: 0, height: 0 };
    const transitionCenter = { x: 0, y: 0, width: 0, height: lineHeight };
    const transitionFinal = { x: 0, y: navHeight, width: 0, height: lineHeight };
    const applyFull = () => {
      const { width, height } = measure();
      transitionFull.width = width;
      transitionFull.height = height;
      gsap.set(rect, { attr: transitionFull, opacity: 1 });
    };
    applyFull();
    const { width, height } = measure();
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const tl = gsap.timeline({
      defaults: { ease: "power3.inOut" },
      onComplete: () => {
        if (!disposed) setIntroComplete(true);
      },
    });
    tl.to(rect, {
      attr: Object.assign(transitionCenter, { y: height / 2 - lineHeight / 2, width }),
      duration: reduceMotion ? 0 : 0.42,
    });
    tl.to(rect, { attr: Object.assign(transitionFinal, { width }), duration: reduceMotion ? 0 : 0.62 });
    tl.to(rect, { opacity: 0, duration: reduceMotion ? 0 : 0.18 });
    const onResize = () => {
      if (disposed || tl.progress() >= 1) return;
      const next = measure();
      gsap.set(rect, {
        attr: { x: 0, y: tl.progress() < 0.45 ? 0 : next.height / 2 - lineHeight / 2, width: next.width, height: tl.progress() < 0.45 ? next.height : lineHeight },
      });
    };
    window.addEventListener("resize", onResize);
    return () => {
      disposed = true;
      window.removeEventListener("resize", onResize);
      tl.kill();
    };
  }, [introTransition]);

  const handleOpenTrace = useCallback((msgId: string, _content: string, evidence: TraceEvidence[]) => {
    setTraceTarget({ msgId, evidence });
  }, []);

  const handleCloseTrace = useCallback(() => {
    setTraceTarget(null);
  }, []);

  return (
    <div className={`main-window-page ${introComplete ? "is-intro-complete" : "is-intro-active"}`}>
      <GlobalTopNav
        currentWindow="main"
        onNavigateToMain={undefined}
        onNavigateToDatabase={onOpenDatabase}
        onNavigateToMacro={onOpenMacro}
        onLogout={onBack}
      />

      <div className="main-window-content-shell">
        {introComplete && <>
        {/* DotGrid: z-index 0, full-screen background */}
        <div className="main-window-dotgrid-bg">
          <DotGrid
            dotSize={2}
            gap={12}
            baseColor="#6b6b6b"
            activeColor="#0047FF"
            proximity={150}
            speedTrigger={100}
            shockRadius={250}
            shockStrength={5}
            maxSpeed={5000}
            resistance={750}
            returnDuration={1.5}
          />
        </div>

        {/* ChatCanvasLines: z-index 5, SVG canvas layer between dotgrid and menu */}
        <div className="main-window-canvas-layer">
          <ChatCanvasLines
            menuOpen={false}
            mode={chatMode}
            onComplete={() => setCanvasReady(true)}
          />
        </div>

        {/* ChatInteractionPanel: z-index 6, interactive chat layer above canvas, pointer-events on children only */}
        <ChatInteractionPanel
          menuOpen={false}
          canvasReady={canvasReady}
          mode={chatMode}
          onModeChange={setChatMode}
          onOpenTrace={handleOpenTrace}
          initialModelConfigState={modelConfigState}
          onModelConfigStateChange={setModelConfigState}
          isSelfCenterNode={isSelfCenterNode}
        />

        {/* TraceWindow: z-index 200, full-screen overlay, mounted only when a trace is active */}
        {traceTarget && (
          <TraceWindow
            msgId={traceTarget.msgId}
            evidence={traceTarget.evidence}
            onClose={handleCloseTrace}
          />
        )}
        </>}
      </div>
      {introTransition === "from-login-loading" && (
        <svg ref={transitionSvgRef} className="main-window-transition-layer" aria-hidden="true">
          <rect ref={transitionRectRef} className="main-window-transition-rect" />
        </svg>
      )}
    </div>
  );
}
