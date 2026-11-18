"use client";
import { useEffect, useRef, useState } from "react";
import { SpringState, settled, stepSpring } from "./spring";

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(mq.matches);
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/** True once the element has scrolled into view (stays true). */
export function useInView<T extends Element>(threshold = 0.2) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setInView(true);
          io.disconnect();
        }
      },
      { threshold },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold]);
  return { ref, inView };
}

/** Spring a vector of numbers toward `targets`. Returns the current values each frame. */
export function useSprings(targets: number[]): number[] {
  const reduced = usePrefersReducedMotion();
  const state = useRef<SpringState[]>(targets.map((x) => ({ x, v: 0 })));
  const target = useRef(targets);
  const raf = useRef<number | null>(null);
  const [values, setValues] = useState(targets);
  target.current = targets;

  useEffect(() => {
    if (reduced) {
      state.current = targets.map((x) => ({ x, v: 0 }));
      setValues(targets);
      return;
    }
    if (raf.current !== null) return;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min(0.032, (now - last) / 1000);
      last = now;
      state.current = state.current.map((s, i) => stepSpring(s, target.current[i], dt));
      setValues(state.current.map((s) => s.x));
      if (state.current.every((s, i) => settled(s, target.current[i]))) {
        raf.current = null;
        return;
      }
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targets.join(","), reduced]);

  useEffect(
    () => () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    },
    [],
  );
  return values;
}
