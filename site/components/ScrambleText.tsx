"use client";
import { ElementType, useEffect, useState } from "react";
import { useInView, usePrefersReducedMotion } from "@/lib/hooks";

const GLYPHS = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789#*<>/+";

/** Decrypt-style reveal: characters settle left to right once the text scrolls into view. */
export default function ScrambleText({
  text,
  as: Tag = "span",
  className = "",
  duration = 900,
}: {
  text: string;
  as?: ElementType;
  className?: string;
  duration?: number;
}) {
  const { ref, inView } = useInView<HTMLElement>(0.4);
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(text);

  useEffect(() => {
    if (!inView || reduced) {
      setShown(text);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const fixed = Math.floor(p * text.length);
      setShown(
        text
          .split("")
          .map((ch, i) => (i < fixed || ch === " " ? ch : GLYPHS[(Math.random() * GLYPHS.length) | 0]))
          .join(""),
      );
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [inView, reduced, text, duration]);

  return (
    <Tag ref={ref} className={className} aria-label={text}>
      <span aria-hidden>{shown}</span>
    </Tag>
  );
}
