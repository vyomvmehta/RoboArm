# RoboArm site (Ishaan's half)

Static showcase site. Next.js (static export), React, Tailwind, Lucide. Lives in `site/` so it can read
`config/*.yaml`, `docs/` and the source files at build time: published numbers cannot drift from the arm.

```
cd site
npm install
npm run dev        # http://localhost:3000
npm run build      # static output in site/out/
```

Vercel: Root Directory `site`, framework Next.js, and turn on "Include files outside the Root Directory"
(the build reads `../config`, `../docs`, `../firmware`, `../arm`, `../tests`, `../README.md`).

## Read before merging

The plan for this site is in "RoboArm website: context and work split". Two points from it still apply:

1. **Sequencing.** Cables and calibration come first. The site cannot be finished before the arm runs:
   there are no renders, photos, video or measured results yet. Every page says so where it matters.
2. **Four things to agree with Vyom** (this branch assumes all four; change them if we agree otherwise):
   - the site lives in this repo under `site/`
   - Next.js static export on Vercel
   - one content file per section, each owned by exactly one person
   - Vyom ships design tokens and the page shell

## Ownership

| Path | Owner | Notes |
| --- | --- | --- |
| `lib/repo.ts`, `lib/arm.ts`, `lib/protocol.ts` | Ishaan | Content loader, build-time config reader, protocol model |
| `content/electronics.md`, `content/software.md`, `content/build-log.md`, `content/failures.ts`, `content/bom.ts` | Ishaan | One file per section |
| `app/electronics`, `app/software`, `app/build-log` | Ishaan | |
| `components/ProtocolExplainer.tsx` | Ishaan | The interactive piece |
| `tailwind.config.ts`, `app/globals.css`, `components/Shell.tsx`, `app/page.tsx` | **Provisional, Vyom's to replace** | Tokens, shell and home page exist so the other pages render. `/mechanical` and `/kinematics` are not started. |

## What is real and what is simulated

- Geometry, limits, speed caps, pulse maths, firmware limits, watchdog and version: read from the repo at build time.
- Code panels: cut from the real files by function name at build time, with real line numbers.
- Build log timeline: generated from `docs/DECISIONS.md`.
- The arm drawing is a schematic computed from `config/arm.yaml`, not a render.
- The serial monitor and protocol explainer run a TypeScript model of `handle_line()`. Nothing is recorded from hardware.
- Load bars use the point-mass model in `docs/TORQUE.md`. An estimate, not a measurement.

## Motion

Rules the site follows (reviewed against the `review-animations`, `choreograph`, `animation-performance`
and `mobile-native` skills):

- **One easing family.** `--ease-out` for entrances, `--ease-in-out` for the line drawings (`app/globals.css`).
- **One entrance per container.** `Stagger` moves its direct children once; nothing inside them animates in again.
  Delays shrink down the group (70, 55, 45 ms ...) and the whole group lands in under 250 ms of delay.
- **Headings rise out of a mask, mono labels decrypt.** `ScrambleText` is for monospace text only, so nothing reflows.
- **Tabs, stage buttons and file buttons switch instantly.** They are clicked repeatedly; only the press (scale 0.97,
  150 ms) and the colour change.
- **Transform and opacity only.** Spotlight glow, load bars, scroll HUD and magnetic buttons all move with `transform`
  and write to the DOM directly, not through React state.
- **The spring** (`lib/spring.ts`, stiffness 120, damping 14) drives the arm pose and the magnetic lean, because both
  get retargeted mid-motion. Panels that do not depend on the pose are memoised.
- **The idle loop stops** when the schematic is off screen or the tab is hidden.
- **Hover styles and the magnetic lean need a real pointer.** `prefers-reduced-motion` keeps the fades and drops movement.

Swapping in Anime.js or Framer Motion means replacing `lib/spring.ts`, `lib/hooks.ts` and `components/Reveal.tsx`.
Not checked: frame timing on a real mid-range phone. Everything above was verified in desktop Chrome only.
