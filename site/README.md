# RoboArm site

The public showcase site for the arm. Next.js with static export: `npm run build` writes plain HTML to `out/`.

## Run it

```
cd site
npm install
npm run dev        # http://localhost:3000
npm run build      # static site in out/
```

## Who owns what

One file, one owner. If two people need to edit the same words, the split is wrong: talk first.

| Path | Owner | What it is |
| --- | --- | --- |
| `styles/tokens.css`, `styles/base.css` | Vyom | Colours, type, spacing; styling for plain HTML |
| `components/ui.tsx`, `SiteHeader`, `SiteFooter` | Vyom | Shared building blocks and the page shell |
| `app/page.tsx`, `content/home.ts`, `components/ArmStage.tsx` | Vyom | Home and its live arm |
| `lib/kinematics.ts` | Vyom | Browser copy of the arm's maths; must match the Python (see below) |
| `lib/armConfig.ts` | Vyom, then the loader | Reads the arm's numbers from `config/*.yaml` at build time; can become an adapter over #17's `loadArm()` |
| `app/mechanical/`, `app/kinematics/` | Vyom | His pages |
| `app/electronics/`, `app/software/`, `app/build-log/` | Ishaan | His pages (not created yet) |
| deploy config, content loader | Ishaan | Vercel, Markdown + `config/*.yaml` reader |
| `lib/site.ts` | shared | Nav list. Flip your page's `ready` to `true` in the PR that adds it |

## Writing a page

1. Create `app/<route>/page.tsx`.
2. Start with `<PageHeader title lead />`, then `<Section>`s.
3. Put ordinary HTML inside `<Prose>`: headings, paragraphs, lists, tables, `pre`, `figure`. It is styled with no class names.
4. Use the building blocks in `components/ui.tsx` for anything else. `/kit/` shows each one.
5. Set `ready: true` for the route in `lib/site.ts`. Until then the nav shows it as plain text and nothing links to it.

## Rules

- **Never hard-code a colour, font size or spacing.** Use the variables in `styles/tokens.css`. That is what keeps light and dark mode and both halves of the site consistent.
- **Numbers about the arm come from `config/*.yaml`,** through the content loader, not typed into a page. The home page already reads them through `lib/armConfig.ts`.
- **Measured values get `className="num"`** (steady-width digits) and always carry their unit. Monospace is only for real machine text: a serial frame, code.
- **House style:** sentence case, no small label above a heading, no cards, no arrows on links. Number things only if they are a real sequence. Yellow means the target or a live value; red means refused. Nothing else uses them.
- **Only claim what is true today.** The status list on the home page is the place to say what is not done.
- Works at phone width with no sideways scrolling; wide tables go in `<div className="table-wrap">`.

## The live arm on the home page

`lib/kinematics.ts` is a copy of the arm's own Python (`arm/kinematics`, `arm/targets.py`, `arm/calibration.py`, `arm/comms/protocol.py`, `arm/motion.py`). If the Python changes, change this too. `npm test` runs both on the same targets and fails if the angles, pulses, frame or refusal message differ (needs Python with the repo's requirements).
