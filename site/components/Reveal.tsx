"use client";
import { Children, CSSProperties, ElementType, ReactNode, isValidElement, cloneElement } from "react";
import { useInView } from "@/lib/hooks";

// Gaps shrink down the group (70, 55, 45, 35 ms ...) so it reads as one wave, not a
// metronome. Anything past the sixth child arrives with the sixth: total stays under 250 ms.
const DELAYS = [0, 70, 125, 170, 205, 230];

/** Group entrance for direct children, triggered once when the group scrolls into view. */
export function Stagger({
  children,
  className = "",
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: ElementType;
}) {
  const { ref, inView } = useInView<HTMLElement>(0.12);
  return (
    <Tag ref={ref} className={`stagger ${inView ? "in" : ""} ${className}`}>
      {Children.map(children, (c, i) =>
        isValidElement<{ style?: CSSProperties }>(c)
          ? cloneElement(c, {
              style: { ...c.props.style, ["--delay" as string]: `${DELAYS[Math.min(i, DELAYS.length - 1)]}ms` } as CSSProperties,
            })
          : c,
      )}
    </Tag>
  );
}

/** Heading that rises out of its own clip box when it scrolls into view. */
export function MaskReveal({ text, as: Tag = "h2", className = "" }: { text: string; as?: ElementType; className?: string }) {
  const { ref, inView } = useInView<HTMLElement>(0.4);
  return (
    <Tag ref={ref} className={`mask ${inView ? "in" : ""} ${className}`}>
      <span>{text}</span>
    </Tag>
  );
}

/** Wrap an inline SVG: shapes with data-draw are stroked in, data-fade elements fade in after. */
export function Draw({ children, className = "" }: { children: ReactNode; className?: string }) {
  const { ref, inView } = useInView<HTMLDivElement>(0.25);
  return (
    <div ref={ref} className={`draw ${inView ? "in" : ""} ${className}`}>
      {children}
    </div>
  );
}
