"use client";
import { useEffect, useRef } from "react";

/** Fixed precision dot grid. Dots near the cursor brighten and lean away slightly. */
export default function DotGrid() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current!;
    const ctx = canvas.getContext("2d")!;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const GAP = 28;
    const R = 150;
    let w = 0;
    let h = 0;
    let raf = 0;
    const mouse = { x: -9999, y: -9999 };
    const eased = { x: -9999, y: -9999 };

    const draw = () => {
      ctx.clearRect(0, 0, w, h);
      for (let y = GAP / 2; y < h; y += GAP) {
        for (let x = GAP / 2; x < w; x += GAP) {
          const dx = x - eased.x;
          const dy = y - eased.y;
          const d = Math.hypot(dx, dy);
          const k = d < R ? 1 - d / R : 0;
          const push = k * k * 5;
          ctx.fillStyle = k > 0 ? `rgba(34,211,238,${0.09 + k * 0.4})` : "rgba(255,255,255,0.075)";
          ctx.beginPath();
          ctx.arc(x + (d ? (dx / d) * push : 0), y + (d ? (dy / d) * push : 0), 1 + k * 0.7, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    };
    const loop = () => {
      eased.x += (mouse.x - eased.x) * 0.14;
      eased.y += (mouse.y - eased.y) * 0.14;
      draw();
      raf = Math.abs(mouse.x - eased.x) + Math.abs(mouse.y - eased.y) > 0.5 ? requestAnimationFrame(loop) : 0;
    };
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      draw();
    };
    const move = (e: PointerEvent) => {
      if (reduced || e.pointerType === "touch") return;
      mouse.x = e.clientX;
      mouse.y = e.clientY;
      if (eased.x < -999) Object.assign(eased, mouse);
      if (!raf) raf = requestAnimationFrame(loop);
    };
    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", move, { passive: true });
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", move);
    };
  }, []);

  return <canvas ref={ref} aria-hidden className="pointer-events-none fixed inset-0 -z-10 h-full w-full" />;
}
