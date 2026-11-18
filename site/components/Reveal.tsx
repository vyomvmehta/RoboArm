"use client";
import { Children, CSSProperties, ElementType, ReactNode, isValidElement, cloneElement } from "react";
import { useInView } from "@/lib/hooks";

/** Staggered entrance for direct children, triggered when the group scrolls into view. */
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
          ? cloneElement(c, { style: { ...c.props.style, ["--i" as string]: i } as CSSProperties })
          : c,
      )}
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
