import type { Metadata } from "next";
import { WiringSchematic } from "@/components/Diagrams";
import { PageHeader, SectionTitle } from "@/components/Shell";
import { Stagger } from "@/components/Reveal";
import { WaveDivider } from "@/components/Accents";
import { content, loadArm } from "@/lib/repo";

export const metadata: Metadata = { title: "Electronics" };

export default function Electronics() {
  const arm = loadArm();
  const [intro, rest] = content("electronics").split("<!-- split -->");
  return (
    <>
      <PageHeader index="01" kicker="Electronics" title="Signals and power" lead="Which wire goes where, what carries current, and the one wiring fault that no amount of firmware can detect." />
      <div className="mx-auto max-w-[1400px] space-y-10 px-4 sm:px-6">
        <div className="prose-arm max-w-3xl" dangerouslySetInnerHTML={{ __html: intro }} />
        <WiringSchematic channels={arm.joints.map((j) => ({ ch: j.channel, label: j.label, servo: j.servo }))} />
      </div>

      <WaveDivider seed={3} className="mt-16" />

      <section className="mx-auto max-w-[1400px] px-4 pt-12 sm:px-6">
        <SectionTitle kicker="Read from the firmware and config at build time" title="Channel map" />
        <Stagger className="grid gap-px bg-white/[0.08] sm:grid-cols-2 lg:grid-cols-5">
          {arm.joints.map((j) => (
            <div key={j.key} className="bg-ink p-5">
              <div className="flex items-baseline justify-between">
                <span className="font-mono text-3xl text-scope">{j.channel}</span>
                <span className="label">channel</span>
              </div>
              <h3 className="mt-6 font-sans text-lg font-medium text-paper">{j.label}</h3>
              <dl className="mt-3 space-y-1 font-mono text-[11px] text-paper/70">
                <div className="flex justify-between"><dt className="text-mute">servo</dt><dd>{j.servo}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">centre</dt><dd>{j.centerUs} µs</dd></div>
                <div className="flex justify-between"><dt className="text-mute">laptop range</dt><dd>{j.minUs}-{j.maxUs}</dd></div>
                <div className="flex justify-between"><dt className="text-mute">speed cap</dt><dd>{j.speedDegPerS} °/s</dd></div>
              </dl>
            </div>
          ))}
        </Stagger>
        <p className="mt-3 font-mono text-[11px] text-mute">
          Channel order is what the sketch writes and what a C frame's five fields mean, in order. Changing one means changing both. Firmware hard limits: {arm.firmware.pulseMin}-
          {arm.firmware.pulseMax} µs on every joint.
        </p>
      </section>

      <div className="mx-auto mt-6 max-w-[1400px] px-4 sm:px-6">
        <div className="prose-arm max-w-3xl" dangerouslySetInnerHTML={{ __html: rest }} />
      </div>
    </>
  );
}
