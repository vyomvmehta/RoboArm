"use client";
import { ButtonHTMLAttributes, useEffect, useRef } from "react";
import { stepSpring, SpringState } from "@/lib/spring";

/**
 * Button that leans toward the cursor and springs back (stiffness 120, damping 14).
 * The lean is decorative, so it is a spring (keeps its velocity when the cursor reverses)
 * and only runs for a fine pointer. The press is on the inner face, so the two transforms
 * never overwrite each other.
 */
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
  const fine = useRef(false);

  useEffect(() => {
    fine.current =
      window.matchMedia("(hover: hover) and (pointer: fine)").matches && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    return () => cancelAnimationFrame(raf.current);
  }, []);

  const run = () => {
    if (raf.current) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - last) / 1000);
      last = now;
      s.current.x = stepSpring(s.current.x, target.current.x, dt);
      s.current.y = stepSpring(s.current.y, target.current.y, dt);
      const { x, y } = s.current;
      const rest =
        Math.abs(x.x - target.current.x) + Math.abs(y.x - target.current.y) + Math.abs(x.v) + Math.abs(y.v) < 0.05;
      if (ref.current) ref.current.style.transform = rest && !target.current.x && !target.current.y ? "" : `translate(${x.x.toFixed(2)}px, ${y.x.toFixed(2)}px)`;
      raf.current = rest ? 0 : requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  };

  return (
    <button
      ref={ref}
      {...rest}
      onPointerMove={(e) => {
        if (!fine.current) return;
        const r = e.currentTarget.getBoundingClientRect();
        target.current = {
          x: (e.clientX - (r.left + r.width / 2)) * 0.2,
          y: (e.clientY - (r.top + r.height / 2)) * 0.3,
        };
        run();
      }}
      onPointerLeave={() => {
        if (!fine.current) return;
        target.current = { x: 0, y: 0 };
        run();
      }}
      className={`group/mag inline-flex ${className}`}
    >
      <span
        className={`hairline inline-flex items-center gap-2 px-3.5 py-2 font-mono text-[11px] uppercase tracking-[0.14em] transition-[color,background-color,border-color,transform] duration-150 ease-crisp group-active/mag:scale-[0.97] ${
          active ? "!border-signal/70 bg-signal/10 text-signal" : "text-paper/75 group-hover/mag:bg-white/5 group-hover/mag:text-paper"
        }`}
      >
        {children}
      </span>
    </button>
  );
}
