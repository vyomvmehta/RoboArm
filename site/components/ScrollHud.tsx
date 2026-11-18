"use client";
import { useEffect, useState } from "react";

/** Floating HUD: page scroll progress drives a joint-angle readout across J1's software limits. */
export default function ScrollHud({ limits }: { limits: [number, number] }) {
  const [p, setP] = useState(0);
  useEffect(() => {
    let raf = 0;
    const read = () => {
      raf = 0;
      const max = document.documentElement.scrollHeight - window.innerHeight;
      setP(max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0);
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
  }, []);

  const angle = limits[0] + p * (limits[1] - limits[0]);
  const a = (angle * Math.PI) / 180;
  const R = 15;
  return (
    <div aria-hidden className="panel pointer-events-none fixed bottom-4 right-4 z-40 hidden items-center gap-3 px-3 py-2 md:flex">
      <svg width="44" height="34" viewBox="-20 -20 40 26">
        <path d={`M ${R * Math.cos((limits[0] * Math.PI) / 180)} ${-R * Math.sin((limits[0] * Math.PI) / 180)} A ${R} ${R} 0 0 0 ${R * Math.cos((limits[1] * Math.PI) / 180)} ${-R * Math.sin((limits[1] * Math.PI) / 180)}`} fill="none" stroke="rgba(255,255,255,0.18)" />
        <line x1="0" y1="0" x2={R * Math.cos(a)} y2={-R * Math.sin(a)} stroke="#FF6A1A" strokeWidth="2" strokeLinecap="round" />
        <circle r="2" fill="#F3F4F6" />
      </svg>
      <div className="font-mono text-[10px] leading-tight">
        <div className="text-mute">SCROLL {String(Math.round(p * 100)).padStart(3, "0")}%</div>
        <div className="tabular-nums text-scope">J1 {angle.toFixed(1)}°</div>
      </div>
    </div>
  );
}
