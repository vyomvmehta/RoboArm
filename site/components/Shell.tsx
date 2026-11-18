import Link from "next/link";
import { GitBranch } from "lucide-react";
import { ReactNode } from "react";
import ScrambleText from "./ScrambleText";

// Provisional page frame. Vyom owns the final shell and tokens (site/README.md).
const NAV = [
  { href: "/electronics/", label: "Electronics" },
  { href: "/software/", label: "Software" },
  { href: "/build-log/", label: "Build log" },
];
export const REPO = "https://github.com/vyomvmehta/RoboArm";

export function Nav() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/[0.08] bg-ink/80 backdrop-blur-md">
      <nav aria-label="Main" className="mx-auto flex max-w-[1400px] items-center justify-between gap-2 px-4 py-3 sm:gap-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2.5 font-mono text-sm font-medium tracking-wide text-paper">
          <span className="inline-block h-2.5 w-2.5 bg-signal" /> ROBOARM
        </Link>
        <ul className="flex items-center sm:gap-2">
          {NAV.map((n) => (
            <li key={n.href}>
              <Link href={n.href} className="whitespace-nowrap px-1.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.06em] text-mute transition-colors hover:text-paper sm:px-3 sm:text-[11px] sm:tracking-[0.14em]">
                {n.label}
              </Link>
            </li>
          ))}
          <li>
            <a href={REPO} className="ml-1 inline-flex p-1.5 text-mute hover:text-paper" aria-label="RoboArm on GitHub">
              <GitBranch size={16} />
            </a>
          </li>
        </ul>
      </nav>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-24 border-t border-white/[0.08]">
      <div className="mx-auto flex max-w-[1400px] flex-col gap-3 px-4 py-8 font-mono text-[11px] text-mute sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <span>RoboArm · Vyom Mehta, Ishaan, Siddharth · University of Waterloo</span>
        <span>
          Numbers on this site are read from <a className="text-paper/80 underline underline-offset-4" href={`${REPO}/tree/main/config`}>config/</a> at build time.{" "}
          <a className="text-paper/80 underline underline-offset-4" href={`${REPO}#how-we-built-this`}>How we built this</a>
        </span>
      </div>
    </footer>
  );
}

export function PageHeader({ index, kicker, title, lead }: { index: string; kicker: string; title: string; lead: ReactNode }) {
  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-10 pt-16 sm:px-6 sm:pt-24">
      <p className="label">
        <span className="text-signal">{index}</span> / {kicker}
      </p>
      <ScrambleText as="h1" text={title} className="mt-4 block font-sans text-4xl font-medium tracking-tight text-paper sm:text-6xl" />
      <p className="mt-5 max-w-2xl text-base leading-relaxed text-paper/70 sm:text-lg">{lead}</p>
    </div>
  );
}

export function SectionTitle({ kicker, title }: { kicker: string; title: string }) {
  return (
    <div className="mb-8">
      <p className="label">{kicker}</p>
      <ScrambleText as="h2" text={title} className="mt-3 block font-sans text-2xl font-medium tracking-tight text-paper sm:text-4xl" />
    </div>
  );
}
