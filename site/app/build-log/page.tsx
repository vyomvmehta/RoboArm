import type { Metadata } from "next";
import SpotlightCard from "@/components/SpotlightCard";
import { PageHeader, SectionTitle } from "@/components/Shell";
import { Stagger } from "@/components/Reveal";
import { WaveDivider } from "@/components/Accents";
import { FAILURES } from "@/content/failures";
import { content, decisions } from "@/lib/repo";

export const metadata: Metadata = { title: "Build log" };

const fmt = (iso: string | null) =>
  iso ? new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-CA", { month: "short", day: "numeric", timeZone: "UTC" }) : "undated";

export default function BuildLog() {
  const log = decisions();
  return (
    <>
      <PageHeader index="03" kicker="Build log" title="Decisions and failures" lead="What we decided, why, and what went wrong on the way. The failures are the useful part." />

      <section className="mx-auto max-w-[1400px] px-4 sm:px-6">
        <SectionTitle kicker="Three that cost us time" title="What went wrong" />
        <Stagger className="grid gap-4 md:grid-cols-3">
          {FAILURES.map((f) => (
            <SpotlightCard key={f.title} tone="signal">
              <p className="label !text-signal">{f.tag}</p>
              <h3 className="mt-3 font-sans text-xl font-medium text-paper">{f.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-paper/70">{f.body}</p>
              <p className="mt-5 font-mono text-[10px] text-mute">{f.source}</p>
            </SpotlightCard>
          ))}
        </Stagger>
      </section>

      <WaveDivider seed={11} className="mt-16" />

      <section className="mx-auto max-w-[1400px] px-4 pt-12 sm:px-6">
        <SectionTitle kicker={`${log.length} entries · generated from docs/DECISIONS.md`} title="Decision timeline" />
        <div className="prose-arm mb-10 max-w-3xl" dangerouslySetInnerHTML={{ __html: content("build-log") }} />
        <ol className="relative ml-2 border-l border-white/[0.12] sm:ml-28">
          {log.map((d) => (
            <li key={d.id} className="relative pb-6 pl-6 sm:pl-10">
              <span className={`absolute -left-[5px] top-2 h-[9px] w-[9px] ${d.status === "on-hold" ? "bg-signal" : d.status === "test" ? "border border-scope bg-ink" : "bg-scope"}`} />
              <span className="font-mono text-[11px] text-mute sm:absolute sm:-left-28 sm:top-1 sm:w-24 sm:text-right">{fmt(d.date)}</span>
              <details className="hairline group bg-panel/70 open:bg-panel">
                <summary className="flex cursor-pointer list-none items-baseline gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
                  <span className="font-mono text-xs text-signal">{d.id}</span>
                  <span className="flex-1 font-sans text-[15px] font-medium text-paper">{d.title}</span>
                  {d.status === "on-hold" && <span className="label !text-signal">on hold</span>}
                  <span className="font-mono text-mute transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="border-t border-white/[0.08] px-4 py-4">
                  {d.meta && <p className="mb-3 font-mono text-[11px] text-mute">{d.meta}</p>}
                  <div className="prose-arm !text-sm" dangerouslySetInnerHTML={{ __html: d.html }} />
                </div>
              </details>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
