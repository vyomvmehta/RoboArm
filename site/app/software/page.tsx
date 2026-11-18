import type { Metadata } from "next";
import ProtocolExplainer from "@/components/ProtocolExplainer";
import CodeView from "@/components/inspector/CodeView";
import { PageHeader, SectionTitle } from "@/components/Shell";
import { WaveDivider } from "@/components/Accents";
import { content, excerpt, loadArm, testCounts } from "@/lib/repo";

export const metadata: Metadata = { title: "Software" };

export default function Software() {
  const arm = loadArm();
  const t = testCounts();
  const html = content("software")
    .replaceAll("{{watchdogMs}}", String(arm.firmware.watchdogMs))
    .replaceAll("{{heartbeatHz}}", String(arm.comms.heartbeatHz))
    .replaceAll("{{fwVersion}}", arm.firmware.version)
    .replaceAll("{{testFunctions}}", String(t.functions))
    .replaceAll("{{testFiles}}", String(t.files));
  const ino = "firmware/arm_controller/arm_controller.ino";
  return (
    <>
      <PageHeader index="02" kicker="Software" title="Protocol and firmware" lead="A text protocol small enough to check by hand, and firmware whose main job is to refuse: bad frames, out-of-range pulses, and a laptop that has gone quiet." />

      <section className="mx-auto max-w-[1400px] px-4 sm:px-6">
        <SectionTitle kicker="Interactive · simulated firmware" title="Send it a frame" />
        <div className="hairline">
          <ProtocolExplainer limits={arm.firmware} />
        </div>
        <p className="mt-3 font-mono text-[11px] text-mute">
          The parser here is a TypeScript model of handle_line() in the sketch. Limits and version are read from the sketch at build time.
        </p>
      </section>

      <WaveDivider seed={7} className="mt-16" />

      <div className="mx-auto grid max-w-[1400px] gap-10 px-4 pt-4 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="prose-arm min-w-0" dangerouslySetInnerHTML={{ __html: html }} />
        <div className="min-w-0 space-y-6 lg:sticky lg:top-20 lg:mt-12 lg:self-start">
          <CodeView file={{ label: "handle_c()", path: ino, lang: "cpp", ...excerpt(ino, /^static void handle_c\(/, /^static void handle_a\(/) }} maxHeight="20rem" />
          <CodeView file={{ label: "watchdog", path: ino, lang: "cpp", ...excerpt(ino, /^static void service_watchdog\(/, /^\/\/ -{10,}/) }} />
          <CodeView file={{ label: "checksum", path: "arm/comms/protocol.py", lang: "python", ...excerpt("arm/comms/protocol.py", /^def checksum\(/, /^def decode\(/) }} />
        </div>
      </div>
    </>
  );
}
