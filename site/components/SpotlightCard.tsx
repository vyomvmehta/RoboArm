"use client";
import { CSSProperties, ReactNode, useRef } from "react";

/**
 * Card whose border and surface glow follow the cursor.
 * The glow is one fixed-size blob per layer, moved with `transform` only (composited, no
 * repaint of the card, no CSS variable recalculated down the subtree). The 1px gap around
 * the inner panel is what shows the bright blob as a border.
 */
export default function SpotlightCard({
  children,
  className = "",
  tone = "scope",
  style,
}: {
  children: ReactNode;
  className?: string;
  tone?: "scope" | "signal";
  style?: CSSProperties;
}) {
  const edge = useRef<HTMLDivElement | null>(null);
  const wash = useRef<HTMLDivElement | null>(null);
  const box = useRef<DOMRect | null>(null);
  const rgb = tone === "signal" ? "255,106,26" : "34,211,238";
  const blob = "pointer-events-none absolute left-0 top-0 opacity-0 transition-opacity duration-200 group-hover:opacity-100";

  const place = (x: number, y: number) => {
    if (edge.current) edge.current.style.transform = `translate(${x - 260}px, ${y - 260}px)`;
    if (wash.current) wash.current.style.transform = `translate(${x - 340}px, ${y - 340}px)`;
  };

  return (
    <div
      onPointerEnter={(e) => {
        if (e.pointerType === "touch") return;
        box.current = e.currentTarget.getBoundingClientRect();
        place(e.clientX - box.current.left, e.clientY - box.current.top);
      }}
      onPointerMove={(e) => {
        if (e.pointerType === "touch") return;
        const r = (box.current ??= e.currentTarget.getBoundingClientRect());
        place(e.clientX - r.left, e.clientY - r.top);
      }}
      onPointerLeave={() => (box.current = null)}
      className={`group relative overflow-hidden bg-white/[0.08] p-px ${className}`}
      style={style}
    >
      <div
        ref={edge}
        aria-hidden
        className={`${blob} h-[520px] w-[520px]`}
        style={{ background: `radial-gradient(closest-side, rgba(${rgb},0.6), transparent)` }}
      />
      <div className="relative h-full overflow-hidden bg-panel p-6">
        <div
          ref={wash}
          aria-hidden
          className={`${blob} h-[680px] w-[680px]`}
          style={{ background: `radial-gradient(closest-side, rgba(${rgb},0.07), transparent)` }}
        />
        <div className="relative">{children}</div>
      </div>
    </div>
  );
}
