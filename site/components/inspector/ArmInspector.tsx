"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { Boxes, Cable, Code2, Crosshair, Eye, Pause, Play } from "lucide-react";
import { ArmData, Pose, TORQUE_SOURCE, chain, holdingTorque, ikPlanar, inRange, posePulses } from "@/lib/arm";
import { usePrefersReducedMotion, useSprings } from "@/lib/hooks";
import { BOM } from "@/content/bom";
import MagneticButton from "../MagneticButton";
import Schematic from "./Schematic";
import CodeView, { CodeFile } from "./CodeView";
import SerialConsole from "./SerialConsole";

type Tab = "overview" | "pinout" | "bom" | "code";
const TABS: { id: Tab; label: string; icon: typeof Eye }[] = [
  { id: "overview", label: "Overview", icon: Eye },
  { id: "pinout", label: "Pinout / Kinematics", icon: Cable },
  { id: "bom", label: "BOM / Specs", icon: Boxes },
  { id: "code", label: "Live control code", icon: Code2 },
];

interface Stage {
  n: number;
  title: string;
  joint: number | null;
  body: (arm: ArmData) => string;
}

const STAGES: Stage[] = [
  {
    n: 1,
    title: "Base servo & yaw",
    joint: 0,
    body: (a) =>
      `J0 turns the whole arm about the vertical axis. IK sets it first: yaw = atan2(y, x), then everything else is solved in the arm's vertical plane. Software limits ${a.joints[0].limits![0]}° to ${a.joints[0].limits![1]}°. The turntable bearings carry the arm's weight, so this servo only fights friction and inertia.`,
  },
  {
    n: 2,
    title: "Shoulder torque & linkage",
    joint: 1,
    body: () =>
      "J1 carries everything beyond it. The worst case is the arm stretched flat holding a 30 g block: the load readout peaks there and falls as the arm folds. The design rule is to stay at or under 50 % of stall, because holding near stall overheats the motor.",
  },
  {
    n: 3,
    title: "Elbow kinematics",
    joint: 2,
    body: () =>
      "The elbow servo sits at the shoulder and drives the forearm through a parallel rod (cyan). So the servo sets the forearm's absolute angle above horizontal, θ1 + θ2, not the bend θ2. The pulse maths in calibration.yaml uses that absolute angle.",
  },
  {
    n: 4,
    title: "End-effector gripper",
    joint: 4,
    body: (a) =>
      `J4 opens and closes a two-jaw gripper between ${a.gripper.closedMm} and ${a.gripper.openMm} mm. The laptop works in millimetres and maps the opening to a pulse on a straight line between two measured points. J3 above it sets the gripper's pitch.`,
  },
  {
    n: 5,
    title: "Inverse kinematics solver",
    joint: null,
    body: () =>
      "Drag anywhere on the schematic. The solver steps back from the target along the gripper to find the wrist point, solves the two-link triangle with the law of cosines, then lets the wrist make up the requested pitch. Targets the arm cannot reach are refused, never clamped.",
  },
];

export default function ArmInspector({ arm, files }: { arm: ArmData; files: CodeFile[] }) {
  const { home, park } = arm.poses;
  const reduced = usePrefersReducedMotion();
  const [tab, setTab] = useState<Tab>("overview");
  const [stage, setStage] = useState(0); // 0 = idle overview loop
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(true);
  const [target, setTarget] = useState<{ r: number; z: number }>({ r: arm.poses.homeTarget.x, z: arm.poses.homeTarget.z });
  const [ikNote, setIkNote] = useState<string | null>(null);
  const [ikPose, setIkPose] = useState<Pose>(home);
  const [file, setFile] = useState(0);

  const script: Pose[] = useMemo(() => {
    switch (stage) {
      case 1:
        return [{ ...home, t0: -60 }, { ...home, t0: 60 }];
      case 2:
        return [{ ...home, t1: 0, t2: 0, t3: 0 }, home];
      case 3:
        return [park, { ...park, t2: -30 }];
      case 4:
        return [{ ...home, grip: arm.gripper.closedMm }, { ...home, grip: arm.gripper.openMm }];
      case 5:
        return [ikPose];
      default:
        return [home, park];
    }
  }, [stage, home, park, ikPose, arm.gripper]);

  useEffect(() => setStep(0), [stage]);
  useEffect(() => {
    if (!playing || reduced || script.length < 2) return;
    const t = setInterval(() => setStep((s) => s + 1), stage === 0 ? 4200 : 2400);
    return () => clearInterval(t);
  }, [playing, reduced, script.length, stage]);

  const goal = script[step % script.length];
  const [t0, t1, t2, t3, grip] = useSprings([goal.t0, goal.t1, goal.t2, goal.t3, goal.grip]);
  const pose: Pose = { t0, t1, t2, t3, grip };
  const poseRef = useRef(pose);
  poseRef.current = pose;

  const onTarget = (r: number, z: number) => {
    setTarget({ r, z });
    const sol = ikPlanar(arm, r, z, arm.poses.homeTarget.pitch);
    if (!sol.ok) return setIkNote(sol.reason);
    const next: Pose = { ...home, t1: sol.t1, t2: sol.t2, t3: sol.t3 };
    if (!inRange(arm, posePulses(arm, next))) return setIkNote("a pulse would leave the calibrated range");
    setIkNote(null);
    setIkPose(next);
  };

  const pulses = posePulses(arm, pose);
  const torque = holdingTorque(arm, pose);
  const tip = chain(arm, pose).tip;
  const activeJoint = stage === 0 ? null : STAGES[stage - 1].joint;
  const angles = [t0, t1, t2, t3];

  return (
    <div className="grid gap-px bg-white/[0.08] lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      {/* ------------------------------------------------ viewport + walkthrough */}
      <div className="flex min-w-0 flex-col bg-ink">
        <div className="flex items-center justify-between border-b border-white/[0.08] px-4 py-2.5">
          <span className="label">Schematic · side view · mm · from config/arm.yaml</span>
          <button
            className="label inline-flex items-center gap-1.5 hover:text-paper"
            onClick={() => setPlaying((p) => !p)}
            aria-pressed={!playing}
            aria-label={playing ? "Pause motion" : "Play motion"}
          >
            {playing ? <Pause size={12} /> : <Play size={12} />} {playing ? "pause" : "play"}
          </button>
        </div>

        <div className="relative aspect-[400/340] w-full">
          <Schematic
            arm={arm}
            pose={pose}
            active={activeJoint}
            showFourBar={stage === 3}
            target={stage === 5 ? target : null}
            targetOk={!ikNote}
            onTarget={stage === 5 ? onTarget : undefined}
          />
          {stage === 5 && (
            <div className="pointer-events-none absolute left-4 top-4 font-mono text-[11px]">
              <div className="text-scope">
                target r {target.r} · z {target.z} · pitch {arm.poses.homeTarget.pitch}°
              </div>
              <div className={ikNote ? "text-red-400" : "text-mute"}>{ikNote ? `unreachable: ${ikNote}` : "reachable, elbow up"}</div>
            </div>
          )}
        </div>

        {/* telemetry strip */}
        <div className="grid grid-cols-5 gap-px border-y border-white/[0.08] bg-white/[0.08]">
          {arm.joints.map((j, i) => {
            const on = activeJoint === i;
            return (
              <div key={j.key} className={`min-w-0 bg-ink px-2 py-2.5 sm:px-3 ${on ? "shadow-[inset_0_2px_0_#FF6A1A]" : ""}`}>
                <div className={`label truncate ${on ? "!text-signal" : ""}`}>{j.label}</div>
                <div className="mt-1 font-mono text-sm tabular-nums text-paper sm:text-base">
                  {i < 4 ? `${angles[i].toFixed(1)}°` : `${grip.toFixed(1)}`}
                  {i === 4 && <span className="text-[10px] text-mute"> mm</span>}
                </div>
                <div className="font-mono text-[10px] tabular-nums text-scope">{pulses[i]} µs</div>
                <div className="mt-1.5 h-0.5 bg-white/10" title={i > 0 && i < 4 ? TORQUE_SOURCE : "No static load modelled"}>
                  <div className={`h-full ${torque[i].pct > 50 ? "bg-red-400" : "bg-signal"}`} style={{ width: `${Math.min(100, torque[i].pct * 2)}%` }} />
                </div>
                <div className="mt-1 font-mono text-[10px] tabular-nums text-mute">{i > 0 && i < 4 ? `${torque[i].pct.toFixed(0)}% stall` : "no load"}</div>
              </div>
            );
          })}
        </div>

        {/* guided walkthrough */}
        <div className="p-4">
          <div className="mb-3 flex flex-wrap gap-2">
            <MagneticButton active={stage === 0} onClick={() => setStage(0)}>
              Idle
            </MagneticButton>
            {STAGES.map((s) => (
              <MagneticButton key={s.n} active={stage === s.n} onClick={() => setStage(s.n)} aria-label={`Stage ${s.n}: ${s.title}`}>
                <span className="text-mute">{s.n}.</span>
                <span className="hidden sm:inline">{s.title}</span>
                <span className="sm:hidden">{s.title.split(" ")[0]}</span>
              </MagneticButton>
            ))}
          </div>
          <div className="min-h-[7.5rem]">
            {stage === 0 ? (
              <p className="max-w-prose text-sm leading-relaxed text-paper/70">
                The arm is cycling between its <span className="text-paper">home</span> pose (ready above the pick zone) and its{" "}
                <span className="text-paper">park</span> pose (where it rests limp when disarmed). Pick a stage to step through one joint at a time. Load bars are a static
                estimate, not a measurement.
              </p>
            ) : (
              <>
                <h3 className="flex items-center gap-2 font-sans text-lg font-medium text-paper">
                  {stage === 5 && <Crosshair size={16} className="text-scope" />}
                  {STAGES[stage - 1].n}. {STAGES[stage - 1].title}
                </h3>
                <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-paper/70">{STAGES[stage - 1].body(arm)}</p>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------ tabbed workbench panel */}
      <div className="flex min-w-0 flex-col bg-ink">
        <div role="tablist" aria-label="Inspector panels" className="flex overflow-x-auto border-b border-white/[0.08]">
          {TABS.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              role="tab"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={`flex shrink-0 flex-1 items-center justify-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-3 font-mono text-[10.5px] uppercase tracking-[0.06em] transition-colors ${
                tab === id ? "border-signal text-paper" : "border-transparent text-mute hover:text-paper"
              }`}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>

        <div role="tabpanel" className="min-w-0 flex-1 p-4 sm:p-5">
          {tab === "overview" && (
            <div className="space-y-5">
              <p className="text-sm leading-relaxed text-paper/75">
                Five hobby servos, an Arduino Nano and a PCA9685, driven by a Python program on a laptop. The laptop solves the inverse kinematics and streams pulse widths; the
                firmware only checks them, applies them and keeps the arm safe when the stream stops.
              </p>
              <dl className="grid grid-cols-2 gap-px bg-white/[0.08] font-mono text-xs">
                {[
                  ["Degrees of freedom", "5 (4 + gripper)"],
                  ["Links l1 / l2 / l3", `${arm.links.l1} / ${arm.links.l2} / ${arm.links.l3} mm`],
                  ["Pick zone radius", `${arm.workspace.rMin}-${arm.workspace.rMax} mm`],
                  ["Firmware", arm.firmware.version],
                  ["Watchdog", `${arm.firmware.watchdogMs} ms`],
                  ["Command rate", `${arm.comms.heartbeatHz} Hz`],
                  ["Tip now (r, z)", `${tip[0].toFixed(0)}, ${tip[1].toFixed(0)} mm`],
                  ["Shoulder load now", `${torque[1].kgcm.toFixed(2)} kg·cm`],
                ].map(([k, v]) => (
                  <div key={k} className="bg-ink p-3">
                    <dt className="label">{k}</dt>
                    <dd className="mt-1 tabular-nums text-paper">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="hairline border-l-2 !border-l-signal bg-signal/[0.04] p-3 text-xs leading-relaxed text-paper/70">
                This is a schematic computed from the repo's config files, not a render or a recording. Geometry and calibration are provisional until the assembled arm is
                measured.
              </p>
            </div>
          )}

          {tab === "pinout" && (
            <div className="space-y-5">
              <div className="overflow-x-auto">
                <table className="w-full font-mono text-xs">
                  <thead>
                    <tr className="label text-left">
                      {["CH", "Joint", "Servo", "Limits", "µs/°", "Pulse"].map((h) => (
                        <th key={h} className="border-b border-white/15 px-2 py-2 font-normal">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {arm.joints.map((j, i) => (
                      <tr key={j.key} className={activeJoint === i ? "bg-signal/10 text-paper" : "text-paper/80"}>
                        <td className="border-b border-white/[0.06] px-2 py-2 text-scope">{j.channel}</td>
                        <td className="whitespace-nowrap border-b border-white/[0.06] px-2 py-2">{j.label}</td>
                        <td className="border-b border-white/[0.06] px-2 py-2">{j.servo}</td>
                        <td className="whitespace-nowrap border-b border-white/[0.06] px-2 py-2">
                          {j.limits ? `${j.limits[0]}° to ${j.limits[1]}°` : `${arm.gripper.closedMm}-${arm.gripper.openMm} mm`}
                        </td>
                        <td className="border-b border-white/[0.06] px-2 py-2">{i < 4 ? j.usPerDeg : "linear"}</td>
                        <td className="border-b border-white/[0.06] px-2 py-2 tabular-nums text-scope">{pulses[i]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <dl className="grid grid-cols-2 gap-px bg-white/[0.08] font-mono text-xs sm:grid-cols-4">
                {[
                  ["Nano A4", "SDA"],
                  ["Nano A5", "SCL"],
                  ["I2C address", arm.firmware.i2cAddr],
                  ["PWM frame", `${arm.firmware.pwmHz} Hz`],
                ].map(([k, v]) => (
                  <div key={k} className="bg-ink p-3">
                    <dt className="label">{k}</dt>
                    <dd className="mt-1 text-paper">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="font-mono text-[11px] leading-relaxed text-mute">
                pulse = direction × µs/° × (angle − window centre) + {arm.joints[0].centerUs} µs. Laptop range {arm.joints[0].minUs}-{arm.joints[0].maxUs} µs sits inside the
                firmware's hard limits {arm.firmware.pulseMin}-{arm.firmware.pulseMax} µs, so the firmware only trips on a bug.
              </p>
            </div>
          )}

          {tab === "bom" && (
            <div className="space-y-5">
              <ul className="divide-y divide-white/[0.06] font-mono text-xs">
                {BOM.map((b) => (
                  <li key={b.part} className="grid grid-cols-[3.2rem_1fr_auto] items-baseline gap-3 py-2">
                    <span className="text-scope">{b.qty}</span>
                    <span className="min-w-0">
                      <span className="text-paper">{b.part}</span>
                      <span className="block truncate font-sans text-[12px] text-mute">{b.role}</span>
                    </span>
                    <span className={b.status === "planned" ? "text-signal" : "text-paper/60"}>{b.status}</span>
                  </li>
                ))}
              </ul>
              <dl className="grid grid-cols-2 gap-px bg-white/[0.08] font-mono text-xs">
                {[
                  ["Speed cap J0-J2", `${arm.joints[0].speedDegPerS} °/s`],
                  ["Speed cap J3-J4", `${arm.joints[3].speedDegPerS} °/s`],
                  ["Shoulder axis height", `${arm.links.shoulderHeight} mm`],
                  ["Servo rail", "6.0 V"],
                ].map(([k, v]) => (
                  <div key={k} className="bg-ink p-3">
                    <dt className="label">{k}</dt>
                    <dd className="mt-1 text-paper">{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {tab === "code" && (
            <div className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {files.map((f, i) => (
                  <MagneticButton key={f.path + f.label} active={file === i} onClick={() => setFile(i)}>
                    {f.lang === "python" ? "PY" : "C++"} · {f.label}
                  </MagneticButton>
                ))}
              </div>
              <CodeView file={files[file]} maxHeight="17rem" />
              <SerialConsole arm={arm} poseRef={poseRef} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
