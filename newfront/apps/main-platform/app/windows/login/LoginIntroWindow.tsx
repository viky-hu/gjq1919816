"use client";

import { useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import { gsap } from "gsap";
import { LINE_DRAW_EASE } from "../shared/animation";
import { LoginForm } from "./LoginForm";

gsap.registerPlugin(useGSAP);

type PanelStage = "idle" | "opening" | "open" | "closing";

const SYSTEM_TITLE_PRIMARY = "密态智图——";
const SYSTEM_TITLE_SECONDARY = "联邦知识图谱协同检索引擎";
const BRAND_WORD = "S-Graph";
const CTA_PRIMARY = "点击";
const CTA_SECONDARY = "登录";
const INFO_COPY_LINES = [
  "通过多模态异构数据融合、查询驱动双通道图检索、",
  "联邦共识聚合三大核心技术，在原始数据不出域、",
  "不泄露的安全合规约束下，实现跨节点高精度协同知识推理。",
] as const;
const MICRO_COPY = "SECRET / SECURE / SMART";

interface LoginIntroWindowProps {
  onSignIn: (isAdmin: boolean, account: string, nodeType?: string) => void;
}

export function LoginIntroWindow({ onSignIn }: LoginIntroWindowProps) {
  const [panelStage, setPanelStage] = useState<PanelStage>("idle");

  const panelStageRef = useRef<PanelStage>("idle");
  const pageRef = useRef<HTMLElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const ctaRef = useRef<HTMLButtonElement>(null);
  const panelDimRef = useRef<HTMLDivElement>(null);
  const panelShellRef = useRef<HTMLDivElement>(null);
  const panelFormWrapRef = useRef<HTMLDivElement>(null);
  const bandRef = useRef<SVGRectElement>(null);
  const bandClipRef = useRef<SVGRectElement>(null);
  const topRuleRef = useRef<SVGLineElement>(null);
  const topRuleInvertedRef = useRef<SVGLineElement>(null);
  const brandRef = useRef<SVGTextElement>(null);
  const invertedBrandRef = useRef<SVGTextElement>(null);
  const titlePrimaryRef = useRef<SVGTextElement>(null);
  const titleSecondaryRef = useRef<SVGTextElement>(null);
  const invertedTitlePrimaryRef = useRef<SVGTextElement>(null);
  const invertedTitleSecondaryRef = useRef<SVGTextElement>(null);
  const infoLineOneRef = useRef<SVGTextElement>(null);
  const infoLineTwoRef = useRef<SVGTextElement>(null);
  const infoLineThreeRef = useRef<SVGTextElement>(null);
  const invertedInfoLineOneRef = useRef<SVGTextElement>(null);
  const invertedInfoLineTwoRef = useRef<SVGTextElement>(null);
  const invertedInfoLineThreeRef = useRef<SVGTextElement>(null);
  const microCopyRef = useRef<SVGTextElement>(null);
  const invertedMicroCopyRef = useRef<SVGTextElement>(null);
  const ctaLeftBracketRef = useRef<SVGTextElement>(null);
  const ctaPrimaryRef = useRef<SVGTextElement>(null);
  const ctaSecondaryRef = useRef<SVGTextElement>(null);
  const ctaRightBracketRef = useRef<SVGTextElement>(null);
  const invertedCtaLeftBracketRef = useRef<SVGTextElement>(null);
  const invertedCtaPrimaryRef = useRef<SVGTextElement>(null);
  const invertedCtaSecondaryRef = useRef<SVGTextElement>(null);
  const invertedCtaRightBracketRef = useRef<SVGTextElement>(null);
  const idleTimerRef = useRef<number | null>(null);
  const lastXRef = useRef<number | null>(null);
  const pointerXRef = useRef<number | null>(null);
  const pointerInsideRef = useRef(false);

  useGSAP(
    (_, contextSafe) => {
      const page = pageRef.current;
      const svg = svgRef.current;
      const cta = ctaRef.current;
      const panelDim = panelDimRef.current;
      const panelShell = panelShellRef.current;
      const panelFormWrap = panelFormWrapRef.current;
      const band = bandRef.current;
      const bandClip = bandClipRef.current;
      const topRule = topRuleRef.current;
      const topRuleInverted = topRuleInvertedRef.current;

      const titleNodes = [
        [titlePrimaryRef.current, titleSecondaryRef.current],
        [invertedTitlePrimaryRef.current, invertedTitleSecondaryRef.current],
      ];
      const infoNodes = [
        [infoLineOneRef.current, infoLineTwoRef.current, infoLineThreeRef.current],
        [
          invertedInfoLineOneRef.current,
          invertedInfoLineTwoRef.current,
          invertedInfoLineThreeRef.current,
        ],
      ];
      const brandNodes = [brandRef.current, invertedBrandRef.current];
      const microNodes = [microCopyRef.current, invertedMicroCopyRef.current];
      const ctaNodes = [
        [
          ctaLeftBracketRef.current,
          ctaPrimaryRef.current,
          ctaSecondaryRef.current,
          ctaRightBracketRef.current,
        ],
        [
          invertedCtaLeftBracketRef.current,
          invertedCtaPrimaryRef.current,
          invertedCtaSecondaryRef.current,
          invertedCtaRightBracketRef.current,
        ],
      ];

      if (
        !page ||
        !svg ||
        !cta ||
        !panelDim ||
        !panelShell ||
        !panelFormWrap ||
        !band ||
        !bandClip ||
        !topRule ||
        !topRuleInverted
      ) {
        return;
      }

      const withContextSafe = <T extends (...args: never[]) => void>(callback: T) =>
        contextSafe ? contextSafe(callback) : callback;

      const setStage = (stage: PanelStage) => {
        panelStageRef.current = stage;
        setPanelStage(stage);
      };

      const devicePixelRatio = window.devicePixelRatio || 1;
      const lineWidth = 1 / devicePixelRatio;
      const snapToDevicePixel = (value: number) =>
        Math.round(value * devicePixelRatio) / devicePixelRatio;
      const clamp = (value: number, min: number, max: number) =>
        Math.min(Math.max(value, min), max);
      const clampX = (value: number) => clamp(value, 0, window.innerWidth);
      const panelWidthInPx = 10 * (96 / 2.54);
      const getExpandedWidth = () =>
        snapToDevicePixel(Math.min(Math.max(window.innerWidth * 0.074, 72), 122));
      const getPanelWidth = () =>
        snapToDevicePixel(Math.min(window.innerWidth, panelWidthInPx));
      const getPanelCenterX = () =>
        snapToDevicePixel(window.innerWidth - getPanelWidth() / 2);
      const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
      ).matches;
      const initialX = snapToDevicePixel(window.innerWidth * 0.5);
      const visualState = {
        centerX: initialX,
        width: lineWidth,
      };
      let pointerMoveTween: gsap.core.Tween | null = null;
      let pointerWidthTween: gsap.core.Tween | null = null;
      let bandTween: gsap.core.Tween | null = null;
      let closeTimeline: gsap.core.Timeline | null = null;

      const renderBand = () => {
        const width = snapToDevicePixel(visualState.width);
        const x = snapToDevicePixel(clampX(visualState.centerX) - width / 2);

        page.style.setProperty("--login-panel-left", `${x}px`);
        page.style.setProperty("--login-panel-width", `${width}px`);
        page.style.setProperty(
          "--login-panel-right",
          `${Math.max(window.innerWidth - x - width, 0)}px`,
        );
        page.style.setProperty("--login-panel-height", `${window.innerHeight}px`);

        for (const rect of [band, bandClip]) {
          rect.setAttribute("x", String(x));
          rect.setAttribute("y", "0");
          rect.setAttribute("width", String(width));
          rect.setAttribute("height", String(window.innerHeight));
        }
      };

      const syncVisualStateFromRenderedBand = () => {
        const renderedX = Number(band.getAttribute("x"));
        const renderedWidth = Number(band.getAttribute("width"));

        if (!Number.isFinite(renderedX) || !Number.isFinite(renderedWidth)) {
          return;
        }

        visualState.width = snapToDevicePixel(renderedWidth);
        visualState.centerX = snapToDevicePixel(renderedX + renderedWidth / 2);
      };

      const renderStaticLayout = () => {
        svg.setAttribute("viewBox", `0 0 ${window.innerWidth} ${window.innerHeight}`);
        const cm = window.innerWidth / 19;
        const horizontalInset = snapToDevicePixel(cm);
        const titleX = snapToDevicePixel(cm * 1.5);
        const brandX = snapToDevicePixel(titleX - clamp(window.innerWidth * 0.012, 14, 24));
        const ruleY = snapToDevicePixel(cm * 1.5);
        const brandY = snapToDevicePixel(ruleY - clamp(window.innerWidth * 0.022, 24, 42));
        const centerY = snapToDevicePixel(window.innerHeight * 0.5);
        const titleBaselineGap = 136;
        const copyLowerOffset = snapToDevicePixel(cm * 0.5);
        const microLowerOffset = snapToDevicePixel(cm * 0.08);
        const infoStartY = snapToDevicePixel(
          centerY + titleBaselineGap / 2 + clamp(window.innerWidth * 0.07, 96, 138) + copyLowerOffset,
        );
        const infoLineGap = snapToDevicePixel(clamp(window.innerWidth * 0.014, 22, 30));
        const microY = snapToDevicePixel(
          infoStartY + infoLineGap * 2 + clamp(window.innerWidth * 0.03, 36, 56) + microLowerOffset,
        );
        const ctaGap = clamp(window.innerWidth * 0.0085, 8, 14);
        const ctaRightInset = clamp(window.innerWidth * 0.036, 28, 58);
        const ctaBottomInset = clamp(window.innerWidth * 0.032, 24, 54);
        const ctaLineGap = snapToDevicePixel(
          (window.innerWidth <= 720 ? 36 : 46) * 1.18,
        );
        const ctaCenterY = snapToDevicePixel(
          window.innerHeight - ctaBottomInset - ctaLineGap * 0.5,
        );

        for (const line of [topRule, topRuleInverted]) {
          line.setAttribute("x1", String(horizontalInset));
          line.setAttribute(
            "x2",
            String(snapToDevicePixel(window.innerWidth - horizontalInset)),
          );
          line.setAttribute("y1", String(ruleY));
          line.setAttribute("y2", String(ruleY));
        }

        for (const brand of brandNodes) {
          if (!brand) {
            continue;
          }

          brand.setAttribute("x", String(brandX));
          brand.setAttribute("y", String(brandY));
        }

        for (const [primary, secondary] of titleNodes) {
          if (!primary || !secondary) {
            continue;
          }

          primary.setAttribute("x", String(titleX));
          primary.setAttribute(
            "y",
            String(snapToDevicePixel(centerY - titleBaselineGap / 2 - 20)),
          );
          secondary.setAttribute("x", String(titleX));
          secondary.setAttribute(
            "y",
            String(snapToDevicePixel(centerY + titleBaselineGap / 2 - 20)),
          );
        }

        for (const lines of infoNodes) {
          const [lineOne, lineTwo, lineThree] = lines;
          if (!lineOne || !lineTwo || !lineThree) {
            continue;
          }

          lineOne.setAttribute("x", String(titleX));
          lineOne.setAttribute("y", String(infoStartY));
          lineTwo.setAttribute("x", String(titleX));
          lineTwo.setAttribute("y", String(snapToDevicePixel(infoStartY + infoLineGap)));
          lineThree.setAttribute("x", String(titleX));
          lineThree.setAttribute(
            "y",
            String(snapToDevicePixel(infoStartY + infoLineGap * 2)),
          );
        }

        for (const micro of microNodes) {
          if (!micro) {
            continue;
          }

          micro.setAttribute("x", String(titleX));
          micro.setAttribute("y", String(microY));
        }

        for (const [leftBracket, primary, secondary, rightBracket] of ctaNodes) {
          if (!leftBracket || !primary || !secondary || !rightBracket) {
            continue;
          }

          primary.setAttribute("x", "0");
          primary.setAttribute(
            "y",
            String(snapToDevicePixel(ctaCenterY - ctaLineGap / 2)),
          );
          secondary.setAttribute("x", "0");
          secondary.setAttribute(
            "y",
            String(snapToDevicePixel(ctaCenterY + ctaLineGap / 2)),
          );

          const primaryWidth = primary.getComputedTextLength();
          const secondaryWidth = secondary.getComputedTextLength();
          const textBlockWidth = Math.max(primaryWidth, secondaryWidth);

          leftBracket.setAttribute("x", "0");
          rightBracket.setAttribute("x", "0");
          const bracketWidth = Math.max(
            leftBracket.getComputedTextLength(),
            rightBracket.getComputedTextLength(),
          );
          const totalWidth = bracketWidth * 2 + ctaGap * 2 + textBlockWidth;
          const leftEdge = snapToDevicePixel(
            window.innerWidth - ctaRightInset - totalWidth,
          );
          const textCenterX = snapToDevicePixel(
            leftEdge + bracketWidth + ctaGap + textBlockWidth / 2,
          );
          const leftBracketX = snapToDevicePixel(leftEdge + bracketWidth / 2);
          const rightBracketX = snapToDevicePixel(
            window.innerWidth - ctaRightInset - bracketWidth / 2,
          );

          leftBracket.setAttribute("x", String(leftBracketX));
          leftBracket.setAttribute("y", String(ctaCenterY));
          primary.setAttribute("x", String(textCenterX));
          secondary.setAttribute("x", String(textCenterX));
          rightBracket.setAttribute("x", String(rightBracketX));
          rightBracket.setAttribute("y", String(ctaCenterY));
        }

        const ctaBounds = {
          left: Number(ctaLeftBracketRef.current?.getBBox().x ?? 0),
          top: Math.min(
            Number(ctaPrimaryRef.current?.getBBox().y ?? 0),
            Number(ctaLeftBracketRef.current?.getBBox().y ?? 0),
          ),
          right:
            Number(ctaRightBracketRef.current?.getBBox().x ?? 0) +
            Number(ctaRightBracketRef.current?.getBBox().width ?? 0),
          bottom: Math.max(
            Number(ctaSecondaryRef.current?.getBBox().y ?? 0) +
              Number(ctaSecondaryRef.current?.getBBox().height ?? 0),
            Number(ctaLeftBracketRef.current?.getBBox().y ?? 0) +
              Number(ctaLeftBracketRef.current?.getBBox().height ?? 0),
          ),
        };

        cta.style.left = `${snapToDevicePixel(ctaBounds.left - 12)}px`;
        cta.style.top = `${snapToDevicePixel(ctaBounds.top - 10)}px`;
        cta.style.width = `${snapToDevicePixel(ctaBounds.right - ctaBounds.left + 24)}px`;
        cta.style.height = `${snapToDevicePixel(ctaBounds.bottom - ctaBounds.top + 20)}px`;
      };

      const clearPointerTweens = () => {
        pointerMoveTween?.kill();
        pointerWidthTween?.kill();
        pointerMoveTween = null;
        pointerWidthTween = null;
      };

      const clearBandTween = () => {
        bandTween?.kill();
        bandTween = null;
      };

      const clearCloseTimeline = () => {
        closeTimeline?.kill();
        closeTimeline = null;
      };

      const clearIdleTimer = () => {
        if (idleTimerRef.current !== null) {
          window.clearTimeout(idleTimerRef.current);
          idleTimerRef.current = null;
        }
      };

      const collapseAtCurrentX = () => {
        if (panelStageRef.current !== "idle") {
          return;
        }

        pointerWidthTween?.kill();
        pointerWidthTween = gsap.to(visualState, {
          width: lineWidth,
          duration: prefersReducedMotion ? 0 : 0.32,
          ease: "power3.out",
          onUpdate: renderBand,
          onComplete: () => {
            visualState.width = lineWidth;
            renderBand();
            pointerWidthTween = null;
          },
        });
      };

      const armIdleCollapse = () => {
        clearIdleTimer();
        idleTimerRef.current = window.setTimeout(collapseAtCurrentX, 1000);
      };

      const rememberPointerX = (value: number) => {
        const nextX = snapToDevicePixel(clampX(value));
        pointerInsideRef.current = true;
        pointerXRef.current = nextX;
        return nextX;
      };

      const getTrackedPointerX = () =>
        snapToDevicePixel(
          clampX(pointerInsideRef.current ? (pointerXRef.current ?? visualState.centerX) : visualState.centerX),
        );

      const focusLoginInput = () => {
        window.requestAnimationFrame(() => {
          const input = document.getElementById("sv-account") as HTMLInputElement | null;
          input?.focus();
        });
      };

      gsap.set(panelDim, { autoAlpha: 0 });
      gsap.set(panelShell, { autoAlpha: 0 });
      gsap.set(panelFormWrap, { autoAlpha: 0, y: 18 });

      const openTimeline = gsap.timeline({
        paused: true,
        onStart: () => {
          clearIdleTimer();
          setStage("opening");
        },
        onComplete: () => {
          setStage("open");
          focusLoginInput();
        },
      });

      openTimeline
        .to(
          panelDim,
          {
            autoAlpha: 1,
            duration: prefersReducedMotion ? 0 : 0.18,
            ease: "power1.out",
          },
          0.04,
        )
        .to(
          panelShell,
          {
            autoAlpha: 1,
            duration: prefersReducedMotion ? 0 : 0.01,
          },
          0.1,
        )
        .to(
          panelFormWrap,
          {
            autoAlpha: 1,
            y: 0,
            duration: prefersReducedMotion ? 0 : 0.28,
            ease: "power2.out",
          },
          0.2,
        );

      const resetClosedPanelVisuals = () => {
        openTimeline.pause(0);
        gsap.set(panelDim, { autoAlpha: 0 });
        gsap.set(panelShell, { autoAlpha: 0 });
        gsap.set(panelFormWrap, { autoAlpha: 0, y: 18 });
      };

      const ctaLeftBrackets = [
        ctaLeftBracketRef.current,
        invertedCtaLeftBracketRef.current,
      ].filter(Boolean) as SVGTextElement[];
      const ctaRightBrackets = [
        ctaRightBracketRef.current,
        invertedCtaRightBracketRef.current,
      ].filter(Boolean) as SVGTextElement[];

      const hoverCtaIn = withContextSafe(() => {
        if (panelStageRef.current !== "idle") {
          return;
        }

        gsap.to(ctaLeftBrackets, {
          x: -5,
          duration: 0.18,
          ease: "power2.out",
          overwrite: true,
        });
        gsap.to(ctaRightBrackets, {
          x: 5,
          duration: 0.18,
          ease: "power2.out",
          overwrite: true,
        });
      });

      const hoverCtaOut = withContextSafe(() => {
        gsap.to([...ctaLeftBrackets, ...ctaRightBrackets], {
          x: 0,
          duration: 0.16,
          ease: "power2.out",
          overwrite: true,
        });
      });

      const openPanel = withContextSafe(() => {
        if (panelStageRef.current !== "idle") {
          return;
        }

        hoverCtaOut();
        clearIdleTimer();
        clearPointerTweens();
        clearBandTween();
        clearCloseTimeline();
        renderBand();
        openTimeline.invalidate().play(0);
        bandTween = gsap.to(visualState, {
          width: getPanelWidth(),
          centerX: getPanelCenterX(),
          duration: prefersReducedMotion ? 0 : 0.48,
          ease: LINE_DRAW_EASE,
          onUpdate: renderBand,
          onComplete: () => {
            visualState.width = getPanelWidth();
            visualState.centerX = getPanelCenterX();
            renderBand();
            bandTween = null;
          },
        });
      });

      const closePanel = withContextSafe(() => {
        if (panelStageRef.current === "idle" || panelStageRef.current === "closing") {
          return;
        }

        clearIdleTimer();
        clearPointerTweens();
        clearBandTween();
        clearCloseTimeline();
        setStage("closing");
        syncVisualStateFromRenderedBand();

        const closeStart = {
          centerX: visualState.centerX,
          width: visualState.width,
          progress: 0,
        };
        const renderClosingBand = () => {
          const targetX = getTrackedPointerX();
          visualState.centerX = snapToDevicePixel(
            gsap.utils.interpolate(closeStart.centerX, targetX, closeStart.progress),
          );
          visualState.width = snapToDevicePixel(
            gsap.utils.interpolate(closeStart.width, lineWidth, closeStart.progress),
          );
          renderBand();
        };

        closeTimeline = gsap.timeline({
          onComplete: () => {
            const restingX = getTrackedPointerX();
            lastXRef.current = restingX;
            visualState.centerX = restingX;
            visualState.width = lineWidth;
            renderBand();
            resetClosedPanelVisuals();
            closeTimeline = null;
            setStage("idle");
          },
        });

        closeTimeline
          .to(
            panelFormWrap,
            {
              autoAlpha: 0,
              y: 18,
              duration: prefersReducedMotion ? 0 : 0.16,
              ease: "power2.in",
            },
            0,
          )
          .to(
            panelDim,
            {
              autoAlpha: 0,
              duration: prefersReducedMotion ? 0 : 0.16,
              ease: "power1.in",
            },
            0.04,
          )
          .to(
            panelShell,
            {
              autoAlpha: 0,
              duration: prefersReducedMotion ? 0 : 0.01,
            },
            prefersReducedMotion ? 0 : 0.14,
          )
          .to(
            closeStart,
            {
              progress: 1,
              duration: prefersReducedMotion ? 0 : 0.34,
              ease: LINE_DRAW_EASE,
              onUpdate: renderClosingBand,
            },
            prefersReducedMotion ? 0 : 0.12,
          );
      });

      const followPointer = (event: PointerEvent) => {
        const nextX = rememberPointerX(event.clientX);

        if (panelStageRef.current !== "idle") {
          return;
        }

        clearBandTween();
        clearCloseTimeline();
        clearPointerTweens();
        gsap.killTweensOf(visualState);
        syncVisualStateFromRenderedBand();
        renderBand();
        lastXRef.current = nextX;
        const expandedWidth = getExpandedWidth();

        pointerMoveTween = gsap.to(visualState, {
          centerX: nextX,
          duration: prefersReducedMotion ? 0 : 0.46,
          ease: "power3.out",
          onUpdate: renderBand,
          onComplete: () => {
            visualState.centerX = nextX;
            renderBand();
            pointerMoveTween = null;
          },
        });

        pointerWidthTween = gsap.to(visualState, {
          width: expandedWidth,
          duration: prefersReducedMotion ? 0 : 0.32,
          ease: "power3.out",
          onUpdate: renderBand,
          onComplete: () => {
            visualState.width = expandedWidth;
            pointerWidthTween = null;
          },
        });
        armIdleCollapse();
      };

      const leavePage = () => {
        pointerInsideRef.current = false;

        if (panelStageRef.current !== "idle") {
          return;
        }

        clearIdleTimer();
        collapseAtCurrentX();
      };

      const syncOnResize = () => {
        renderStaticLayout();

        if (panelStageRef.current === "idle") {
          if (lastXRef.current !== null) {
            const nextX = snapToDevicePixel(clampX(lastXRef.current));
            lastXRef.current = nextX;
            visualState.centerX = nextX;
          }

          renderBand();
          return;
        }

        visualState.width = getPanelWidth();
        visualState.centerX = getPanelCenterX();
        renderBand();
      };

      const handleKeyDown = (event: KeyboardEvent) => {
        if (event.key !== "Escape") {
          return;
        }

        if (panelStageRef.current === "idle") {
          return;
        }

        event.preventDefault();
        closePanel();
      };

      page.addEventListener("pointerenter", followPointer);
      page.addEventListener("pointerleave", leavePage);
      page.addEventListener("pointercancel", leavePage);
      window.addEventListener("blur", leavePage);
      window.addEventListener("pointermove", followPointer);
      window.addEventListener("resize", syncOnResize);
      window.addEventListener("keydown", handleKeyDown);
      cta.addEventListener("pointerenter", hoverCtaIn);
      cta.addEventListener("pointerleave", hoverCtaOut);
      cta.addEventListener("focus", hoverCtaIn);
      cta.addEventListener("blur", hoverCtaOut);
      cta.addEventListener("click", openPanel);

      lastXRef.current = initialX;
      pointerXRef.current = initialX;
      setStage("idle");
      renderStaticLayout();
      renderBand();

      return () => {
        clearIdleTimer();
        page.removeEventListener("pointerenter", followPointer);
        page.removeEventListener("pointerleave", leavePage);
        page.removeEventListener("pointercancel", leavePage);
        window.removeEventListener("blur", leavePage);
        window.removeEventListener("pointermove", followPointer);
        window.removeEventListener("resize", syncOnResize);
        window.removeEventListener("keydown", handleKeyDown);
        cta.removeEventListener("pointerenter", hoverCtaIn);
        cta.removeEventListener("pointerleave", hoverCtaOut);
        cta.removeEventListener("focus", hoverCtaIn);
        cta.removeEventListener("blur", hoverCtaOut);
        cta.removeEventListener("click", openPanel);
        clearPointerTweens();
        clearBandTween();
        clearCloseTimeline();
        openTimeline.kill();
        gsap.killTweensOf(visualState);
        gsap.killTweensOf([...ctaLeftBrackets, ...ctaRightBrackets]);
      };
    },
    { scope: pageRef },
  );

  return (
    <main
      ref={pageRef}
      className="login-placeholder-page"
      data-panel-stage={panelStage}
    >
      <svg ref={svgRef} className="login-hover-band-svg" aria-hidden="true">
        <defs>
          <clipPath id="login-band-text-clip" clipPathUnits="userSpaceOnUse">
            <rect
              ref={bandClipRef}
              x={0}
              y={0}
              width={1}
              height="100%"
              shapeRendering="crispEdges"
            />
          </clipPath>
        </defs>

        <line
          ref={topRuleRef}
          className="login-placeholder-top-rule"
          x1={0}
          x2={0}
          y1={0}
          y2={0}
        />

        <g className="login-brand-mark">
          <text ref={brandRef} className="login-brand-mark-word">
            {BRAND_WORD}
          </text>
        </g>

        <g className="login-system-title">
          <text ref={titlePrimaryRef} className="login-system-title-line">
            {SYSTEM_TITLE_PRIMARY}
          </text>
          <text ref={titleSecondaryRef} className="login-system-title-line">
            {SYSTEM_TITLE_SECONDARY}
          </text>
        </g>

        <g className="login-support-copy">
          <text ref={infoLineOneRef} className="login-support-copy-line">
            {INFO_COPY_LINES[0]}
          </text>
          <text ref={infoLineTwoRef} className="login-support-copy-line">
            {INFO_COPY_LINES[1]}
          </text>
          <text ref={infoLineThreeRef} className="login-support-copy-line">
            {INFO_COPY_LINES[2]}
          </text>
        </g>

        <g className="login-micro-copy">
          <text ref={microCopyRef} className="login-micro-copy-line">
            {MICRO_COPY}
          </text>
        </g>

        <g className="login-cta-title">
          <text ref={ctaLeftBracketRef} className="login-cta-bracket">
            [
          </text>
          <text ref={ctaPrimaryRef} className="login-cta-line">
            {CTA_PRIMARY}
          </text>
          <text ref={ctaSecondaryRef} className="login-cta-line">
            {CTA_SECONDARY}
          </text>
          <text ref={ctaRightBracketRef} className="login-cta-bracket">
            ]
          </text>
        </g>

        <rect
          ref={bandRef}
          className="login-hover-band"
          x={0}
          y={0}
          width={1}
          height="100%"
          shapeRendering="crispEdges"
        />

        <line
          ref={topRuleInvertedRef}
          className="login-placeholder-top-rule is-inverted"
          clipPath="url(#login-band-text-clip)"
          x1={0}
          x2={0}
          y1={0}
          y2={0}
        />

        <g className="login-brand-mark is-inverted" clipPath="url(#login-band-text-clip)">
          <text ref={invertedBrandRef} className="login-brand-mark-word">
            {BRAND_WORD}
          </text>
        </g>

        <g className="login-system-title is-inverted" clipPath="url(#login-band-text-clip)">
          <text ref={invertedTitlePrimaryRef} className="login-system-title-line">
            {SYSTEM_TITLE_PRIMARY}
          </text>
          <text ref={invertedTitleSecondaryRef} className="login-system-title-line">
            {SYSTEM_TITLE_SECONDARY}
          </text>
        </g>

        <g className="login-support-copy is-inverted" clipPath="url(#login-band-text-clip)">
          <text ref={invertedInfoLineOneRef} className="login-support-copy-line">
            {INFO_COPY_LINES[0]}
          </text>
          <text ref={invertedInfoLineTwoRef} className="login-support-copy-line">
            {INFO_COPY_LINES[1]}
          </text>
          <text ref={invertedInfoLineThreeRef} className="login-support-copy-line">
            {INFO_COPY_LINES[2]}
          </text>
        </g>

        <g className="login-micro-copy is-inverted" clipPath="url(#login-band-text-clip)">
          <text ref={invertedMicroCopyRef} className="login-micro-copy-line">
            {MICRO_COPY}
          </text>
        </g>

        <g className="login-cta-title is-inverted" clipPath="url(#login-band-text-clip)">
          <text ref={invertedCtaLeftBracketRef} className="login-cta-bracket">
            [
          </text>
          <text ref={invertedCtaPrimaryRef} className="login-cta-line">
            {CTA_PRIMARY}
          </text>
          <text ref={invertedCtaSecondaryRef} className="login-cta-line">
            {CTA_SECONDARY}
          </text>
          <text ref={invertedCtaRightBracketRef} className="login-cta-bracket">
            ]
          </text>
        </g>
      </svg>

      <div ref={panelDimRef} className="login-panel-dim" aria-hidden="true" />

      <div ref={panelShellRef} className="login-panel-shell" aria-hidden={panelStage === "idle"}>
        <div className="svg-text-content login-panel-text">
          <div ref={panelFormWrapRef} className="login-panel-form-wrap">
            <LoginForm onSignIn={onSignIn} />
          </div>
        </div>
      </div>

      <button
        ref={ctaRef}
        type="button"
        className="login-placeholder-hitarea"
        aria-label="点击登录"
      />
    </main>
  );
}
