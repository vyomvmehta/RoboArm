"use client";
import { ButtonHTMLAttributes, useEffect, useRef } from "react";
import { stepSpring, SpringState } from "@/lib/spring";

/** Button that leans toward the cursor and springs back (stiffness 120, damping 14). */
export default function MagneticButton({
  children,
  className = "",
  active = false,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }) {
  const ref = useRef<HTMLButtonElement | null>(null);
  const target = useRef({ x: 0, y: 0 });
  const s = useRef<{ x: SpringState; y: SpringState }>({ x: { x: 0, v: 0 }, y: { x: 0, v: 0 } });
  const raf = useRef(0);

  const run = () => {
    if (raf.current) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - last) / 1000);
      last = now;
      s.current.x = stepSpring(s.current.x, target.current.x, dt);
      s.current.y = stepSpring(s.current.y, target.current.y, dt);
      const { x, y } = s.current;
      if (ref.current) ref.current.style.transform = `translate(${x.x.toFixed(2)}px, ${y.x.toFixed(2)}px)`;
      const rest =
        Math.abs(x.x - target.current.x) + Math.abs(y.x - target.current.y) + Math.abs(x.v) + Math.abs(y.v) < 0.05;
      raf.current = rest ? 0 : requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  return (
    <button
      ref={ref}
      {...rest}
      onPointerMove={(e) => {
        if (e.pointerType === "touch" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
        const r = e.currentTarget.getBoundingClientRect();
        target.current = {
          x: (e.clientX - (r.left + r.width / 2)) * 0.25,
          y: (e.clientY - (r.top + r.height / 2)) * 0.35,
        };
        run();
      }}
      onPointerLeave={() => {
        target.current = { x: 0, y: 0 };
        run();
      }}
      className={`hairline inline-flex items-center gap-2 px-3.5 py-2 font-mono text-[11px] uppercase tracking-[0.14em] transition-colors duration-200 active:scale-[0.97] ${
        active ? "border-signal/70 bg-signal/10 text-signal" : "text-paper/75 hover:bg-white/5 hover:text-paper"
      } ${className}`}
    >
      {children}
    </button>
  );
}
