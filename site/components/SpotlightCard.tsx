"use client";
import { CSSProperties, ReactNode, useRef } from "react";

/** Card whose border and surface glow follow the cursor. */
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
  const ref = useRef<HTMLDivElement | null>(null);
  const rgb = tone === "signal" ? "255,106,26" : "34,211,238";
  return (
    <div
      ref={ref}
      onPointerMove={(e) => {
        const r = ref.current!.getBoundingClientRect();
        ref.current!.style.setProperty("--mx", `${e.clientX - r.left}px`);
        ref.current!.style.setProperty("--my", `${e.clientY - r.top}px`);
      }}
      className={`group relative overflow-hidden bg-panel/80 p-px ${className}`}
      style={style}
    >
      <div
        aria-hidden
        className="absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: `radial-gradient(260px circle at var(--mx) var(--my), rgba(${rgb},0.55), transparent 65%)` }}
      />
      <div aria-hidden className="hairline absolute inset-0" />
      <div className="relative h-full bg-panel p-6">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ background: `radial-gradient(340px circle at var(--mx) var(--my), rgba(${rgb},0.07), transparent 60%)` }}
        />
        <div className="relative">{children}</div>
      </div>
    </div>
  );
}
