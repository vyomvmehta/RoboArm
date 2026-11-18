// One damped spring, integrated with semi-implicit Euler. Every animated value on the site
// goes through this (or the CSS `ease-crisp` curve), so swapping in Anime.js or Framer
// Motion later means replacing this file and useSprings() and nothing else.

export const SPRING = { stiffness: 120, damping: 14, mass: 1 } as const;

export interface SpringState {
  x: number;
  v: number;
}

export function stepSpring(s: SpringState, target: number, dt: number, cfg = SPRING): SpringState {
  const a = (-cfg.stiffness * (s.x - target) - cfg.damping * s.v) / cfg.mass;
  const v = s.v + a * dt;
  return { x: s.x + v * dt, v };
}

export function settled(s: SpringState, target: number, eps = 0.01): boolean {
  return Math.abs(s.x - target) < eps && Math.abs(s.v) < eps;
}
