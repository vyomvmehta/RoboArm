import Link from "next/link";
import { ArrowUpRight, Cpu, Eye, Zap, Cog } from "lucide-react";
import ArmInspector from "@/components/inspector/ArmInspector";
import { CodeFile } from "@/components/inspector/CodeView";
import ScrambleText from "@/components/ScrambleText";
import SpotlightCard from "@/components/SpotlightCard";
import { Draw, Stagger } from "@/components/Reveal";
import { SectionTitle } from "@/components/Shell";
import { CalibrationRings, IsoGrid, WaveDivider } from "@/components/Accents";
import { excerpt, loadArm } from "@/lib/repo";

// Provisional home page. The doc gives `/` to Vyom; this exists so the inspector has
// somewhere to live and the other pages have something to link from. Replace freely.
export default function Home() {
  const arm = loadArm();
  const files: CodeFile[] = [
    { label: "ik()", path: "arm/kinematics/kinematics.py", lang: "python", ...excerpt("arm/kinematics/kinematics.py", /^def ik\(/, /^def |^class /) },
    { label: "joint_to_pulse()", path: "arm/calibration.py", lang: "python", ...excerpt("arm/calibration.py", /^def joint_to_pulse\(/, /^def |^class |^@/) },
    { label: "handle_c()", path: "firmware/arm_controller/arm_controller.ino", lang: "cpp", ...excerpt("firmware/arm_controller/arm_controller.ino", /^static void handle_c\(/, /^static void handle_a\(/) },
    { label: "watchdog", path: "firmware/arm_controller/arm_controller.ino", lang: "cpp", ...excerpt("firmware/arm_controller/arm_controller.ino", /^static void service_watchdog\(/, /^\/\/ -{10,}/) },
  ];
  const reach = arm.links.l1 + arm.links.l2 + arm.links.l3;

  const modules = [
    {
      icon: Cog,
      tone: "signal" as const,
      kicker: "Actuators",
      title: "Five servos",
      body: "Three MG996R for base, shoulder and elbow. Two MG90S for wrist and gripper. Every unit sweeps 180° between 450 and 2500 µs.",
      spec: `${arm.joints[0].usPerDeg} µs/°`,
    },
    {
      icon: Cpu,
      tone: "scope" as const,
      kicker: "Microcontroller",
      title: "Nano + PCA9685",
      body: `The Nano parses frames, enforces four safety states and a ${arm.firmware.watchdogMs} ms watchdog. The PCA9685 at ${arm.firmware.i2cAddr} generates the ${arm.firmware.pwmHz} Hz pulses.`,
      spec: arm.firmware.version,
    },
    {
      icon: Zap,
      tone: "signal" as const,
      kicker: "Power distribution",
      title: "6.0 V servo rail",
      body: "USB-C PD trigger into an LM2596 buck converter. The Nano is powered separately from USB; all grounds are one net.",
      spec: "fuse + switch planned",
    },
    {
      icon: Eye,
      tone: "scope" as const,
      kicker: "Vision tracking",
      title: "V2: hand gestures",
      body: "Planned, not built. A webcam and MediaPipe will replace the web page as the input. Protocol, IK, calibration and firmware stay the same.",
      spec: "planned",
    },
  ];

  const pages = [
    { href: "/electronics/", n: "01", title: "Electronics", body: "Pin map, power path and the ground return that software cannot see." },
    { href: "/software/", n: "02", title: "Software", body: "The serial protocol, the state machine, and a frame you can type and send." },
    { href: "/build-log/", n: "03", title: "Build log", body: "Every decision in order, including the ones that turned out wrong." },
  ];

  return (
    <>
      <section className="relative mx-auto max-w-[1400px] px-4 pt-10 sm:px-6 sm:pt-12">
        <IsoGrid className="pointer-events-none absolute right-0 top-0 -z-10 hidden h-72 w-[36rem] lg:block" />
        <Stagger>
          <p className="label">
            <span className="text-signal">●</span> In build · University of Waterloo Mechatronics · Nov 2026
          </p>
          <h1 className="mt-5 max-w-4xl font-sans text-5xl font-medium leading-[0.95] tracking-tight text-paper sm:text-7xl">
            <ScrambleText text="RoboArm" duration={700} />
          </h1>
          <p className="mt-6 max-w-2xl text-lg leading-relaxed text-paper/70">
            A five-servo desktop robot arm, designed in SolidWorks and 3D printed. Type a point on a web page and inverse kinematics moves the gripper there. Below is the arm
            as its own config files describe it.
          </p>
        </Stagger>

        <div className="hairline mt-8">
          <ArmInspector arm={arm} files={files} />
        </div>
        <p className="mt-3 font-mono text-[11px] text-mute">
          Status, 16 Nov 2026: electronics and firmware are bench-tested; the arm is not assembled yet. Photos, renders and measured results will replace this schematic when it
          runs.
        </p>
      </section>

      <WaveDivider seed={2} className="mt-20" />

      <section className="mx-auto max-w-[1400px] px-4 pt-16 sm:px-6">
        <SectionTitle kicker="Signal chain" title="From a typed point to a pulse" />
        <Draw className="hairline overflow-x-auto bg-ink/80 p-4 sm:p-6">
          <svg viewBox="0 0 1000 150" className="min-w-[760px]" role="img" aria-label="Signal chain: web page, laptop Python with inverse kinematics, USB serial, Arduino Nano, I2C, PCA9685, five servos">
            {[
              ["Web page", "sliders · point-and-go"],
              ["Laptop · Python", "target → IK → pulses"],
              ["Arduino Nano", "parse · guard · watchdog"],
              ["PCA9685", `${arm.firmware.pwmHz} Hz PWM`],
              ["5 servos", "J0 to J4"],
            ].map(([t, s], i) => (
              <g key={t} style={{ ["--d" as string]: i * 2 }}>
                <rect data-draw pathLength={1} x={i * 205} y={40} width={160} height={64} fill="#10141A" stroke={i === 2 ? "#FF6A1A" : "rgba(243,244,246,0.7)"} />
                <text data-fade x={i * 205 + 80} y={68} textAnchor="middle" className="font-mono" fontSize="12" fill="#F3F4F6">
                  {t}
                </text>
                <text data-fade x={i * 205 + 80} y={86} textAnchor="middle" className="font-mono" fontSize="9" fill="#8B94A3">
                  {s}
                </text>
                {i < 4 && (
                  <>
                    <path data-draw pathLength={1} d={`M${i * 205 + 160} 72 H${i * 205 + 205}`} stroke="#22D3EE" strokeWidth="1.4" style={{ ["--d" as string]: i * 2 + 1 }} />
                    <text data-fade x={i * 205 + 182} y={62} textAnchor="middle" className="font-mono" fontSize="8.5" fill="#22D3EE" style={{ ["--d" as string]: i * 2 + 1 }}>
                      {["HTTP", "USB serial", "I2C", "PWM"][i]}
                    </text>
                  </>
                )}
              </g>
            ))}
            <path data-draw pathLength={1} d="M80 122 H900" stroke="rgba(255,255,255,0.2)" strokeDasharray="0" style={{ ["--d" as string]: 9 }} />
            <text data-fade x={80} y={138} className="font-mono" fontSize="9" fill="#8B94A3" style={{ ["--d" as string]: 9 }}>
              V2 swaps the web page for a webcam and hand tracking. Everything to the right stays the same.
            </text>
          </svg>
        </Draw>
      </section>

      <section className="relative mx-auto max-w-[1400px] px-4 pt-24 sm:px-6">
        <CalibrationRings size={300} className="pointer-events-none absolute -top-6 right-6 -z-10 hidden opacity-70 lg:block" />
        <SectionTitle kicker="Hardware modules" title="What is on the bench" />
        <Stagger className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {modules.map((m) => (
            <SpotlightCard key={m.title} tone={m.tone}>
              <div className="flex items-start justify-between">
                <m.icon size={20} className={m.tone === "signal" ? "text-signal" : "text-scope"} />
                <span className="label">{m.spec}</span>
              </div>
              <p className="label mt-8">{m.kicker}</p>
              <h3 className="mt-1.5 font-sans text-xl font-medium text-paper">{m.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-paper/65">{m.body}</p>
            </SpotlightCard>
          ))}
        </Stagger>
      </section>

      <WaveDivider seed={5} className="mt-24" />

      <section className="mx-auto max-w-[1400px] px-4 pt-16 sm:px-6">
        <SectionTitle kicker={`Full stretch ${reach} mm · pick zone ${arm.workspace.rMin}-${arm.workspace.rMax} mm`} title="Go deeper" />
        <Stagger className="grid gap-px bg-white/[0.08] md:grid-cols-3">
          {pages.map((p) => (
            <Link key={p.href} href={p.href} className="group block bg-ink p-6 transition-colors hover:bg-panel sm:p-8">
              <div className="flex items-center justify-between">
                <span className="font-mono text-xs text-signal">{p.n}</span>
                <ArrowUpRight size={18} className="text-mute transition-transform duration-300 ease-crisp group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:text-paper" />
              </div>
              <h3 className="mt-10 font-sans text-2xl font-medium text-paper">{p.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-paper/65">{p.body}</p>
            </Link>
          ))}
        </Stagger>
      </section>
    </>
  );
}
