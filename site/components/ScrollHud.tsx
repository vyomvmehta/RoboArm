"use client";
import { useEffect, useRef } from "react";

/**
 * Floating HUD: page scroll progress drives a joint-angle readout across J1's software limits.
 * Scroll-linked, so it tracks the scroll position 1:1 with no easing, and writes straight to
 * the DOM: a scroll handler that set React state would render on every frame.
 */
export default function ScrollHud({ limits }: { limits: [number, number] }) {
  const needle = useRef<SVGGElement | null>(null);
  const pct = useRef<HTMLSpanElement | null>(null);
  const deg = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      const p = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
      const angle = limits[0] + p * (limits[1] - limits[0]);
      if (needle.current) needle.current.style.transform = `rotate(${-angle}deg)`;
      if (pct.current) pct.current.textContent = String(Math.round(p * 100)).padStart(3, "0");
      if (deg.current) deg.current.textContent = angle.toFixed(1);
    };
    const on = () => {
      if (!raf) raf = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      cancelAnimationFrame(raf);
    };
  }, [limits]);

  const R = 15;
  const pt = (d: number) => `${R * Math.cos((d * Math.PI) / 180)} ${-R * Math.sin((d * Math.PI) / 180)}`;
  return (
    <div aria-hidden className="panel pointer-events-none fixed bottom-4 right-4 z-40 hidden items-center gap-3 px-3 py-2 md:flex">
      <svg width="44" height="34" viewBox="-20 -20 40 26">
        <path d={`M ${pt(limits[0])} A ${R} ${R} 0 0 0 ${pt(limits[1])}`} fill="none" stroke="rgba(255,255,255,0.18)" />
        <g ref={needle} style={{ transform: `rotate(${-limits[0]}deg)` }}>
          <line x1="0" y1="0" x2={R} y2="0" stroke="#FF6A1A" strokeWidth="2" strokeLinecap="round" />
        </g>
        <circle r="2" fill="#F3F4F6" />
      </svg>
      <div className="font-mono text-[10px] leading-tight">
        <div className="text-mute">
          SCROLL <span ref={pct}>000</span>%
        </div>
        <div className="tabular-nums text-scope">
          J1 <span ref={deg}>{limits[0].toFixed(1)}</span>°
        </div>
      </div>
    </div>
  );
}
