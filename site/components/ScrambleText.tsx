"use client";
import { ElementType, useEffect, useRef } from "react";
import { useInView } from "@/lib/hooks";

const GLYPHS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#*<>/+";

/**
 * Decrypt-style reveal for monospace labels: characters settle left to right once the
 * text scrolls into view. Use it on mono text only, where every glyph is the same width
 * and nothing reflows. Writes to the DOM node directly, so React does not render per frame.
 */
export default function ScrambleText({
  text,
  as: Tag = "span",
  className = "",
  duration = 500,
}: {
  text: string;
  as?: ElementType;
  className?: string;
  duration?: number;
}) {
  const { ref, inView } = useInView<HTMLElement>(0.4);
  const out = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    const el = out.current;
    if (!el || !inView) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const fixed = Math.floor(p * text.length);
      let s = text.slice(0, fixed);
      for (let i = fixed; i < text.length; i++) {
        const ch = text[i];
        s += /[A-Za-z0-9]/.test(ch) ? GLYPHS[(Math.random() * GLYPHS.length) | 0] : ch;
      }
      el.textContent = p < 1 ? s : text;
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf);
      el.textContent = text;
    };
  }, [inView, text, duration]);

  return (
    <Tag ref={ref} className={className} aria-label={text}>
      <span ref={out} aria-hidden>
        {text}
      </span>
    </Tag>
  );
}
