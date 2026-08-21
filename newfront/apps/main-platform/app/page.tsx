"use client";

import { useEffect, useState } from "react";

type CanvasSize = {
  height: number;
  width: number;
};

function getCanvasSize(): CanvasSize {
  return {
    height: window.innerHeight,
    width: window.innerWidth,
  };
}

export default function HomePage() {
  const [canvasSize, setCanvasSize] = useState<CanvasSize>({ height: 1, width: 1 });

  useEffect(() => {
    const updateCanvasSize = () => setCanvasSize(getCanvasSize());

    updateCanvasSize();
    window.addEventListener("resize", updateCanvasSize);
    return () => window.removeEventListener("resize", updateCanvasSize);
  }, []);

  return (
    <svg
      aria-label="Empty canvas"
      className="empty-svg-canvas"
      preserveAspectRatio="none"
      role="img"
      viewBox={`0 0 ${canvasSize.width} ${canvasSize.height}`}
    />
  );
}
