"use client";

import { useEffect, useRef, useState } from "react";
import { gsap } from "gsap";
import {
  BRAND_BLUE,
  GRID_COLOR,
  VW,
  VH,
  PHASE1_STROKE,
  INTRO_COORDS,
  COLLAPSE_COORDS,
  FULLSCREEN_COORDS,
  getLineExitCoords,
  GRID_V,
  GRID_H,
} from "../shared/coords";
import { LINE_DRAW_EASE, LOGO_DRAW_EASE } from "../shared/animation";
import {
  logoPath,
  getLogoDiamonds,
  updateLines,
  updateClipRect,
  updatePanelFill,
  updatePanelLayout,
  updateLogoPosition,
} from "./utils";
import { LoginForm } from "./LoginForm";
import { LoginSplitLoadingTip, type LoginSplitLoadingTipPhase } from "./LoginSplitLoadingTip";
import { createLoginLoadingSessionController } from "./login-loading-session";
import { createLoginLoadingTipSequence, type LoginLoadingTipPresentation } from "./login-loading-tip-sequence";
import { LOGIN_LOADING_TIPS } from "./login-loading-tips";

const LOADING_CELL_PATTERN = [0, 1, 2, 1, 2, 2, 3, 3, 4] as const;
const LOADING_LINE_COORDS = {
  x1: 0,
  y1: VH / 2 - 1,
  x2: VW,
  y2: VH / 2 + 1,
};

interface LoginIntroWindowProps {
  onSignIn: (isAdmin: boolean, account: string, nodeType?: string) => void;
  onLoadingComplete?: () => void;
}

export function LoginIntroWindow({ onSignIn, onLoadingComplete }: LoginIntroWindowProps) {
  const pageRef = useRef<HTMLElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const coordsRef = useRef({ ...INTRO_COORDS });
  const canTriggerRef = useRef(false);
  const playedRef = useRef(false);
  const loadingPlayedRef = useRef(false);
  const loadingTriggerRef = useRef<(() => void) | null>(null);
  const loadingSessionRef = useRef(createLoginLoadingSessionController());
  const loadingSequenceRef = useRef(createLoginLoadingTipSequence());
  const loadingTimersRef = useRef<number[]>([]);
  const loadingFinishRef = useRef(false);
  const loadingExitHandlerRef = useRef<() => void>(() => {});
  const onLoadingCompleteRef = useRef(onLoadingComplete);
  const [inverted, setInverted] = useState(false);
  const [animationReady, setAnimationReady] = useState(false);
  const [loadingActive, setLoadingActive] = useState(false);
  const [loadingState, setLoadingState] = useState<"idle" | "blue-complete" | "complete">("idle");
  const [loadingTip, setLoadingTip] = useState(LOGIN_LOADING_TIPS[0]);
  const [loadingTipPhase, setLoadingTipPhase] = useState<LoginSplitLoadingTipPhase>("hold");

  onLoadingCompleteRef.current = onLoadingComplete;

  const handleSignIn = (isAdmin: boolean, account: string, nodeType?: string) => {
    onSignIn(isAdmin, account, nodeType);
    loadingTriggerRef.current?.();
  };

  const clearLoadingTimers = () => {
    loadingTimersRef.current.forEach((timer) => window.clearTimeout(timer));
    loadingTimersRef.current = [];
  };

  useEffect(() => {
    const svg = svgRef.current;
    const page = pageRef.current;
    if (!svg || !page) return;

    const coords = coordsRef.current;
    const mainLines = svg.querySelectorAll<SVGLineElement>(".main-line");
    const logoLines = svg.querySelectorAll<SVGPathElement>(".logo-stroke");
    const gridLines = svg.querySelectorAll<SVGLineElement>(".ref-grid");
    const clipRect = svg.querySelector<SVGRectElement>("#clip-rect");
    const panelRect = svg.querySelector<SVGRectElement>("#panel-fill");
    const introPanel = svg.querySelector<SVGForeignObjectElement>("#intro-panel");
    const loginPanel = svg.querySelector<SVGForeignObjectElement>("#login-panel");
    const hintLayer = svg.querySelector<SVGGElement>("#hint-layer");
    const logoGroup = svg.querySelector<SVGGElement>("#logo-group");
    const logoFill = svg.querySelector<SVGGElement>("#logo-fill");
    const logoOutline = svg.querySelector<SVGGElement>("#logo-outline");
    const lineLengths: number[] = [];
    const logoLineLengths: number[] = [];

    let introTl: gsap.core.Timeline | null = null;
    let stage2Tl: gsap.core.Timeline | null = null;
    let loadingTl: gsap.core.Timeline | null = null;
    let loadingCollapseTl: gsap.core.Timeline | null = null;
    let introClockTime = 0;
    let introTickerAttached = false;
    let introTickerHasTicked = false;
    let introVisibleReady = false;
    let introStartScheduled = false;
    let introCompleted = false;
    let disposed = false;
    let removeInteractionListeners = () => {};
    let removeIntroTicker = () => {};
    const pendingRafs = new Set<number>();
    const pendingTimers = new Set<number>();

    canTriggerRef.current = false;
    playedRef.current = false;
    loadingPlayedRef.current = false;
    loadingTriggerRef.current = null;
    setAnimationReady(false);

    const mark = (name: string) => {
      if (
        process.env.NODE_ENV !== "production" &&
        typeof window !== "undefined" &&
        typeof window.performance?.mark === "function"
      ) {
        window.performance.mark(`login-intro-${name}`);
      }
    };

    const writeDebugSnapshot = (time: number) => {
      if (process.env.NODE_ENV === "production") return;
      page.dataset.introTime = time.toFixed(4);
      page.dataset.introLineLengths = lineLengths.map((length) => length.toFixed(2)).join(",");
      page.dataset.introLineOffsets = Array.from(mainLines)
        .map((line) => line.style.strokeDashoffset || getComputedStyle(line).strokeDashoffset)
        .join(",");
      page.dataset.introLogoLengths = logoLineLengths.map((length) => length.toFixed(2)).join(",");
      page.dataset.introLogoOffsets = Array.from(logoLines)
        .map((line) => line.style.strokeDashoffset || getComputedStyle(line).strokeDashoffset)
        .join(",");
      page.dataset.introPanelSize = panelRect
        ? `${panelRect.getAttribute("width") ?? "0"}x${panelRect.getAttribute("height") ?? "0"}`
        : "0x0";
    };

    const requestManagedFrame = (callback: FrameRequestCallback) => {
      let id = 0;
      id = window.requestAnimationFrame((time) => {
        pendingRafs.delete(id);
        callback(time);
      });
      pendingRafs.add(id);
      return id;
    };

    const requestManagedTimeout = (callback: () => void, delay: number) => {
      let id = 0;
      id = window.setTimeout(() => {
        pendingTimers.delete(id);
        callback();
      }, delay);
      pendingTimers.add(id);
      return id;
    };

    const cancelPendingWork = () => {
      pendingRafs.forEach((id) => window.cancelAnimationFrame(id));
      pendingRafs.clear();
      pendingTimers.forEach((id) => window.clearTimeout(id));
      pendingTimers.clear();
    };

    const applyCoords = (nextCoords: typeof coords, syncPanelFill = true) => {
      updateLines(svg, nextCoords);
      updateClipRect(clipRect, nextCoords);
      if (syncPanelFill) updatePanelFill(panelRect, nextCoords);
      updatePanelLayout(introPanel, loginPanel, nextCoords);
      updateLogoPosition(logoGroup, nextCoords);
    };

    const scheduleLoadingTimer = (callback: () => void, delay: number) => {
      const timer = window.setTimeout(() => {
        loadingTimersRef.current = loadingTimersRef.current.filter((item) => item !== timer);
        callback();
      }, delay);
      loadingTimersRef.current.push(timer);
    };

    const finishLoading = () => {
      if (disposed || loadingFinishRef.current) return;
      loadingFinishRef.current = true;
      clearLoadingTimers();
      setLoadingTipPhase("exit");
      setLoadingActive(false);
      loadingCollapseTl?.kill();
      loadingCollapseTl = gsap.timeline({
        defaults: { ease: "power3.inOut" },
        onComplete: () => {
          if (disposed) return;
          setLoadingState("complete");
          if (process.env.NODE_ENV !== "production") page.dataset.loadingState = "complete";
          mark("loading-completed");
          onLoadingCompleteRef.current?.();
        },
      });
      loadingCollapseTl.to(coords, {
        ...LOADING_LINE_COORDS,
        duration: 0.56,
        onUpdate: () => applyCoords(coords),
      });
      if (panelRect) {
        loadingCollapseTl.to(panelRect, { attr: { y: VH / 2 - 1, height: 2 }, duration: 0.56 }, 0);
      }
    };

    const presentLoadingTip = (presentation: LoginLoadingTipPresentation, sessionId: number) => {
      if (disposed || !loadingSessionRef.current.activateTip(sessionId, presentation.tip.id)) return;
      setLoadingTip(presentation.tip);
      setLoadingTipPhase("enter");
      scheduleLoadingTimer(() => {
        if (!loadingSessionRef.current.markRevealComplete(sessionId, presentation.tip.id)) return;
        setLoadingTipPhase("hold");
        scheduleLoadingTimer(() => {
          if (loadingSessionRef.current.isRevealComplete(sessionId, presentation.tip.id)) {
            setLoadingTipPhase("exit");
          }
        }, presentation.holdMs);
      }, presentation.entranceMs);
    };

    const handleLoadingTipExit = () => {
      const snapshot = loadingSessionRef.current.getSnapshot();
      if (disposed || !snapshot.tipId || !loadingSessionRef.current.acceptExit(snapshot.sessionId, snapshot.tipId)) return;
      const next = loadingSequenceRef.current.advanceAfterExit();
      if (next.kind === "complete") {
        finishLoading();
      } else {
        presentLoadingTip(next.presentation, snapshot.sessionId);
      }
    };
    loadingExitHandlerRef.current = handleLoadingTipExit;

    const beginLoadingSequence = () => {
      if (disposed || loadingFinishRef.current) return;
      clearLoadingTimers();
      setLoadingActive(true);
      setLoadingState("blue-complete");
      if (process.env.NODE_ENV !== "production") page.dataset.loadingState = "blue-complete";
      const sessionId = loadingSessionRef.current.begin();
      const first = loadingSequenceRef.current.start();
      if (first.kind === "tip") presentLoadingTip(first.presentation, sessionId);
      else finishLoading();
    };

    const applyIntroEndState = () => {
      gsap.set(gridLines, { opacity: 0.55 });
      gsap.set(mainLines, { strokeDashoffset: 0 });
      gsap.set(logoLines, { strokeDashoffset: 0 });
      gsap.set(introPanel, { autoAlpha: 1, y: coords.y1 + 16 });
      gsap.set(loginPanel, { autoAlpha: 0 });
      gsap.set(hintLayer, { autoAlpha: 1 });
      if (logoFill) {
        gsap.set(logoFill, { fillOpacity: 1 });
      }
      if (logoOutline) {
        gsap.set(logoOutline, { stroke: BRAND_BLUE });
      }
      if (panelRect) {
        gsap.set(panelRect, {
          fill: "#ffffff",
          attr: {
            x: coords.x1,
            y: coords.y1,
            width: coords.x2 - coords.x1,
            height: coords.y2 - coords.y1,
          },
        });
      }
      applyCoords(coords);
    };

    const context = gsap.context(() => {
      try {
        const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

        lineLengths.push(...Array.from(mainLines, (line) => line.getTotalLength()));
        logoLineLengths.push(...Array.from(logoLines, (line) => line.getTotalLength()));

        gsap.set(gridLines, { opacity: 0.55 });
        mainLines.forEach((line, index) => {
          gsap.set(line, {
            strokeDasharray: lineLengths[index],
            strokeDashoffset: lineLengths[index],
          });
        });
        logoLines.forEach((line, index) => {
          gsap.set(line, {
            strokeDasharray: logoLineLengths[index],
            strokeDashoffset: logoLineLengths[index],
          });
        });
        gsap.set(introPanel, { autoAlpha: 0, y: coords.y1 + 20 });
        gsap.set(hintLayer, { autoAlpha: 0 });
        gsap.set(loginPanel, { autoAlpha: 0 });
        if (logoFill) gsap.set(logoFill, { fillOpacity: 0 });
        if (panelRect) {
          gsap.set(panelRect, {
            fill: "#ffffff",
            attr: {
              x: (coords.x1 + coords.x2) / 2,
              y: (coords.y1 + coords.y2) / 2,
              width: 0,
              height: 0,
            },
          });
        }
        applyCoords(coords, false);

        // Keep the timeline paused until the SVG has had a visible start frame.
        introTl = gsap.timeline({ paused: true, defaults: { ease: "power2.out" } });

        introTl.to(mainLines, {
          strokeDashoffset: 0,
          duration: 1.08,
          ease: LINE_DRAW_EASE,
          stagger: 0.08,
        }, 0);

        introTl.to(logoLines, {
          strokeDashoffset: 0,
          duration: 0.94,
          ease: LOGO_DRAW_EASE,
          stagger: 0.04,
        }, 0.12);

        if (panelRect) {
          introTl.to(panelRect, {
            attr: {
              x: coords.x1,
              y: coords.y1,
              width: coords.x2 - coords.x1,
              height: coords.y2 - coords.y1,
            },
            duration: 0.72,
            ease: "power3.out",
          }, 0.4);
        }

        if (logoFill) {
          introTl.to(logoFill, { fillOpacity: 1, duration: 0.35 }, 0.74);
        }

        introTl.to(introPanel, {
          autoAlpha: 1,
          y: coords.y1 + 16,
          duration: 0.42,
          ease: "power2.out",
        }, 0.9);

        introTl.to(hintLayer, { autoAlpha: 1, duration: 0.28 }, 1.1);
        introTl.pause(0).render(0);
        writeDebugSnapshot(0);
        mark("prepared");

        // === Phase 2: Inversion + collapse + login switch ===
        stage2Tl = gsap.timeline({ paused: true, defaults: { ease: "power3.inOut" } });

        stage2Tl.to(coords, {
          ...COLLAPSE_COORDS,
          duration: 1.02,
          onUpdate: () => applyCoords(coords),
        }, 0);

        if (panelRect) {
          stage2Tl.to(panelRect, { fill: BRAND_BLUE, duration: 0.54 }, 0.05);
        }
        stage2Tl.to(introPanel, { autoAlpha: 0, duration: 0.22 }, 0.12);
        stage2Tl.to(loginPanel, { autoAlpha: 1, duration: 0.34 }, 0.24);
        stage2Tl.to(hintLayer, { autoAlpha: 0, duration: 0.18 }, 0.03);
        if (logoOutline) {
          stage2Tl.to(logoOutline, { stroke: "#ffffff", duration: 0.45 }, 0.08);
        }
        if (logoFill) {
          stage2Tl.to(logoFill.querySelectorAll("path"), { fill: "#ffffff", duration: 0.45 }, 0.08);
        }
        stage2Tl.call(() => setInverted(true), [], 0.06);

        const loadingLineCoords = { ...FULLSCREEN_COORDS };
        loadingTl = gsap.timeline({ paused: true, defaults: { ease: "power3.inOut" } });
        loadingTl.to([introPanel, loginPanel, hintLayer, logoGroup], {
          autoAlpha: 0,
          duration: 0.22,
        }, 0);
        loadingTl.to(coords, {
          ...FULLSCREEN_COORDS,
          duration: 1.02,
          onUpdate: () => applyCoords(coords),
        }, 0);
        if (panelRect) {
          loadingTl.to(panelRect, { fill: BRAND_BLUE, duration: 0.01 }, 0);
        }
        loadingTl.to(loadingLineCoords, {
          ...getLineExitCoords(FULLSCREEN_COORDS),
          duration: 0.14,
          onUpdate: () => updateLines(svg, loadingLineCoords),
        }, 1.02);
        loadingTl.call(beginLoadingSequence);
        loadingCollapseTl = null;

        const triggerLoading = () => {
          if (!canTriggerRef.current || !playedRef.current || loadingPlayedRef.current || !loadingTl) return;
          loadingPlayedRef.current = true;
          stage2Tl?.progress(1).pause();
          loadingTl.invalidate().restart();
          mark("loading-started");
        };
        loadingTriggerRef.current = triggerLoading;

        const triggerStage2 = () => {
          if (!canTriggerRef.current || playedRef.current || !stage2Tl) return;
          playedRef.current = true;
          if (reduceMotion) {
            stage2Tl.progress(1).pause();
          } else {
            stage2Tl.play(0);
          }
        };
        const onWheel = (e: WheelEvent) => {
          if (e.deltaY !== 0) triggerStage2();
        };
        const onClick = () => triggerStage2();

        window.addEventListener("wheel", onWheel, { passive: true });
        window.addEventListener("click", onClick);
        removeInteractionListeners = () => {
          window.removeEventListener("wheel", onWheel);
          window.removeEventListener("click", onClick);
        };

        removeIntroTicker = () => {
          if (!introTickerAttached) return;
          gsap.ticker.remove(onIntroTicker);
          introTickerAttached = false;
          introTickerHasTicked = false;
        };

        const completeIntro = () => {
          if (introCompleted || !introTl) return;
          introCompleted = true;
          removeIntroTicker();
          introTl.pause(introTl.duration()).render(introTl.duration());
          writeDebugSnapshot(introTl.duration());
          canTriggerRef.current = true;
          mark("completed");
        };

        const onIntroTicker = (_time: number, deltaTime: number) => {
          if (disposed || !introTl || introCompleted) {
            removeIntroTicker();
            return;
          }
          if (document.visibilityState !== "visible") {
            removeIntroTicker();
            return;
          }

          if (!introTickerHasTicked) {
            introTickerHasTicked = true;
            introTl.pause(introClockTime).render(introClockTime);
            writeDebugSnapshot(introClockTime);
            mark("first-progress");
            return;
          }

          const deltaSeconds = Math.min(Math.max(deltaTime, 0), 33) / 1000;
          introClockTime = Math.min(introClockTime + deltaSeconds, introTl.duration());
          introTl.time(introClockTime, false);
          writeDebugSnapshot(introClockTime);
          if (introClockTime >= introTl.duration()) completeIntro();
        };

        const startIntroClock = (restart: boolean) => {
          if (disposed || reduceMotion || !introTl || introCompleted || introTickerAttached) return;
          introStartScheduled = false;
          if (restart) introClockTime = 0;
          introTl.pause(introClockTime).render(introClockTime);
          introTickerHasTicked = false;
          introTickerAttached = true;
          gsap.ticker.add(onIntroTicker);
          if (restart) mark("started");
        };

        const scheduleIntroStart = (restart: boolean) => {
          if (
            disposed ||
            reduceMotion ||
            !introTl ||
            introCompleted ||
            introStartScheduled ||
            introTickerAttached ||
            document.visibilityState !== "visible"
          ) return;

          introStartScheduled = true;
          requestManagedFrame(() => {
            if (disposed || document.visibilityState !== "visible") {
              introStartScheduled = false;
              return;
            }
            requestManagedTimeout(() => {
              if (disposed || document.visibilityState !== "visible") {
                introStartScheduled = false;
                return;
              }
              startIntroClock(restart);
            }, 0);
          });
        };

        const onVisibilityChange = () => {
          if (document.visibilityState !== "visible") {
            removeIntroTicker();
            return;
          }

          if (introVisibleReady && !introCompleted) {
            scheduleIntroStart(false);
          }
        };

        document.addEventListener("visibilitychange", onVisibilityChange);
        const removeVisibilityListener = () => {
          document.removeEventListener("visibilitychange", onVisibilityChange);
        };

        if (reduceMotion) {
          applyIntroEndState();
          setAnimationReady(true);
          canTriggerRef.current = true;
          introCompleted = true;
          writeDebugSnapshot(introTl.duration());
          mark("visible");
        } else {
          introVisibleReady = true;
          introTl.pause(0).render(0);
          setAnimationReady(true);
          mark("visible");
          scheduleIntroStart(true);
        }

        const originalRemoveInteractionListeners = removeInteractionListeners;
        removeInteractionListeners = () => {
          originalRemoveInteractionListeners();
          removeVisibilityListener();
        };
      } catch (error) {
        console.error("[LoginIntroWindow] Failed to initialize intro animation.", error);
        cancelPendingWork();
        removeInteractionListeners();
        try {
          applyIntroEndState();
        } catch (fallbackError) {
          console.error("[LoginIntroWindow] Failed to apply static intro fallback.", fallbackError);
        }
        setAnimationReady(true);
        canTriggerRef.current = true;
        introCompleted = true;
        writeDebugSnapshot(introTl?.duration() ?? 0);
        mark("fallback");
      }
    }, page);

    return () => {
      disposed = true;
      cancelPendingWork();
      removeInteractionListeners();
      introTl?.kill();
      stage2Tl?.kill();
      loadingTl?.kill();
      loadingCollapseTl?.kill();
      clearLoadingTimers();
      context.revert();
      removeIntroTicker();
      canTriggerRef.current = false;
      playedRef.current = false;
      loadingPlayedRef.current = false;
      loadingTriggerRef.current = null;
      loadingExitHandlerRef.current = () => {};
      loadingFinishRef.current = false;
      loadingSessionRef.current.begin();
      loadingSequenceRef.current = createLoginLoadingTipSequence();
      setLoadingActive(false);
      setLoadingState("idle");
      setLoadingTip(LOGIN_LOADING_TIPS[0]);
      setLoadingTipPhase("hold");
      introVisibleReady = false;
      introStartScheduled = false;
      setAnimationReady(false);
    };
  }, []);

  return (
    <main
      ref={pageRef}
      className="login-svg-page"
      data-animation-ready={animationReady ? "true" : "false"}
      data-loading-state={loadingState}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VW} ${VH}`}
        preserveAspectRatio="xMidYMid slice"
        className="login-svg-canvas"
      >
        <defs>
          <clipPath id="text-clip">
            <rect
              id="clip-rect"
              x={INTRO_COORDS.x1}
              y={INTRO_COORDS.y1}
              width={INTRO_COORDS.x2 - INTRO_COORDS.x1}
              height={INTRO_COORDS.y2 - INTRO_COORDS.y1}
            />
          </clipPath>
        </defs>

        {GRID_V.map((x, i) => (
          <line key={`gv-${i}`} className="ref-grid" x1={x} y1={0} x2={x} y2={VH} stroke={GRID_COLOR} strokeWidth={1} />
        ))}
        {GRID_H.map((y, i) => (
          <line key={`gh-${i}`} className="ref-grid" x1={0} y1={y} x2={VW} y2={y} stroke={GRID_COLOR} strokeWidth={1} />
        ))}

        <rect
          id="panel-fill"
          x={(INTRO_COORDS.x1 + INTRO_COORDS.x2) / 2}
          y={(INTRO_COORDS.y1 + INTRO_COORDS.y2) / 2}
          width={0}
          height={0}
          fill="#ffffff"
        />

        <line
          className="main-line"
          id="line-left"
          x1={INTRO_COORDS.x1}
          y1={0}
          x2={INTRO_COORDS.x1}
          y2={VH}
          stroke={BRAND_BLUE}
          strokeWidth={PHASE1_STROKE}
        />
        <line
          className="main-line"
          id="line-right"
          x1={INTRO_COORDS.x2}
          y1={0}
          x2={INTRO_COORDS.x2}
          y2={VH}
          stroke={BRAND_BLUE}
          strokeWidth={PHASE1_STROKE}
        />
        <line
          className="main-line"
          id="line-top"
          x1={0}
          y1={INTRO_COORDS.y1}
          x2={VW}
          y2={INTRO_COORDS.y1}
          stroke={BRAND_BLUE}
          strokeWidth={PHASE1_STROKE}
        />
        <line
          className="main-line"
          id="line-bottom"
          x1={0}
          y1={INTRO_COORDS.y2}
          x2={VW}
          y2={INTRO_COORDS.y2}
          stroke={BRAND_BLUE}
          strokeWidth={PHASE1_STROKE}
        />

        <g id="logo-group">
          <g id="logo-outline">
            {getLogoDiamonds().map((diamond, idx) => (
              <path
                key={`logo-outline-${idx}`}
                className="logo-stroke"
                d={logoPath(diamond.cx, diamond.cy, diamond.size)}
                fill="none"
                stroke={BRAND_BLUE}
                strokeWidth={1.5}
              />
            ))}
          </g>
          <g id="logo-fill" fillOpacity={0}>
            {getLogoDiamonds().map((diamond, idx) => (
              <path
                key={`logo-fill-${idx}`}
                d={logoPath(diamond.cx, diamond.cy, diamond.size)}
                fill={BRAND_BLUE}
              />
            ))}
          </g>
        </g>

        <g clipPath="url(#text-clip)">
          <foreignObject
            id="intro-panel"
            x={INTRO_COORDS.x1 + 16}
            y={INTRO_COORDS.y1 + 25}
            width={INTRO_COORDS.x2 - INTRO_COORDS.x1 - 24}
            height={INTRO_COORDS.y2 - INTRO_COORDS.y1 - 32}
            opacity={0}
          >
            <div className={`svg-text-content ${inverted ? "is-inverted" : ""}`}>
              <div className="svg-intro">
                <h1 className="svg-headline">
                  <span className="svg-headline-main">&nbsp;&nbsp;密态智图</span>
                  <br />
                  <br />
                  <br />
                  <span className="svg-headline-sub">——联邦知识图谱协同检索系统</span>
                </h1>
              </div>
            </div>
          </foreignObject>
          <foreignObject
            id="login-panel"
            x={INTRO_COORDS.x1 + 16}
            y={INTRO_COORDS.y1 + 16}
            width={INTRO_COORDS.x2 - INTRO_COORDS.x1 - 32}
            height={INTRO_COORDS.y2 - INTRO_COORDS.y1 - 32}
            opacity={0}
          >
            <div className="svg-text-content is-inverted">
              {typeof LoginForm === 'function' ? <LoginForm onSignIn={handleSignIn} /> : <div>LoginForm load error</div>}
            </div>
          </foreignObject>
        </g>

        <g id="hint-layer" opacity={0}>
          <text
            x={INTRO_COORDS.x2 - 22}
            y={INTRO_COORDS.y2 - 14}
            textAnchor="end"
            className="svg-scroll-hint"
          >
            ˅˅
          </text>
        </g>
      </svg>

      <div
        className="login-agent-loading-overlay"
        data-loading-active={loadingActive ? "true" : "false"}
        aria-hidden={!loadingActive}
      >
        <div className="login-agent-loading-stack">
          <div className="login-agent-loader" aria-hidden="true">
            {LOADING_CELL_PATTERN.map((delay, index) => (
              <div
                key={`loading-cell-${index}`}
                className={`login-loading-cell login-loading-cell-d-${delay}`}
              />
            ))}
          </div>
          <LoginSplitLoadingTip
            text={loadingTip.text}
            active={loadingActive}
            phase={loadingTipPhase}
            onExitComplete={() => loadingExitHandlerRef.current()}
          />
        </div>
      </div>
    </main>
  );
}
