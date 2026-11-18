"use client";
import { MutableRefObject, useEffect, useRef, useState } from "react";
import { ArmData, Pose, posePulses } from "@/lib/arm";
import { FirmwareSim, encode } from "@/lib/protocol";

interface Line {
  id: number;
  dir: ">" | "<" | "#";
  text: string;
  bad?: boolean;
}

const fmt = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}`.padStart(6);

/**
 * Simulated serial monitor. Frames are built from the pose on screen with the real
 * calibration maths, then answered by the TypeScript model of the firmware's parser.
 * Nothing here is recorded from hardware.
 */
export default function SerialConsole({ arm, poseRef }: { arm: ArmData; poseRef: MutableRefObject<Pose> }) {
  const [lines, setLines] = useState<Line[]>([]);
  const [paused, setPaused] = useState(false);
  const box = useRef<HTMLDivElement | null>(null);
  const pausedRef = useRef(false);
  pausedRef.current = paused;

  useEffect(() => {
    const fw = new FirmwareSim(arm.firmware);
    let id = 0;
    let seq = 0;
    const push = (...l: Omit<Line, "id">[]) => setLines((prev) => [...prev, ...l.map((x) => ({ ...x, id: id++ }))].slice(-60));
    const arm_ = encode("A", ++seq);
    push({ dir: "<", text: fw.banner() }, { dir: ">", text: arm_ }, { dir: "<", text: fw.step(arm_).reply! });

    const t = setInterval(() => {
      if (pausedRef.current || document.hidden) return;
      const p = poseRef.current;
      seq = (seq + 1) % 65536;
      const frame = encode("C", seq, ...posePulses(arm, p));
      const res = fw.step(frame);
      push(
        { dir: "#", text: `J0:${fmt(p.t0)}° J1:${fmt(p.t1)}° J2:${fmt(p.t2)}° J3:${fmt(p.t3)}° G:${p.grip.toFixed(1)}mm` },
        { dir: ">", text: frame },
        { dir: "<", text: res.reply ?? "", bad: !res.ok },
      );
    }, 400);
    return () => clearInterval(t);
  }, [arm, poseRef]);

  useEffect(() => {
    if (box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [lines]);

  return (
    <div className="hairline bg-black/60">
      <div className="flex items-center justify-between border-b border-white/[0.08] px-3 py-2">
        <span className="label flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${paused ? "bg-mute" : "animate-pulse bg-scope"}`} />
          Serial monitor · simulated · {arm.comms.baud} 8N1
        </span>
        <button onClick={() => setPaused((p) => !p)} className="label hover:text-paper" aria-pressed={paused}>
          {paused ? "resume" : "pause"}
        </button>
      </div>
      <div ref={box} className="h-44 overflow-y-auto px-3 py-2 font-mono text-[11px] leading-[1.6]" aria-live="off">
        {lines.map((l) => (
          <div key={l.id} className={l.dir === "#" ? "text-mute" : l.bad ? "text-red-400" : l.dir === ">" ? "text-paper/85" : "text-scope"}>
            <span className="mr-2 select-none text-white/30">{l.dir === "#" ? " " : l.dir}</span>
            <span className="whitespace-pre">{l.text}</span>
          </div>
        ))}
      </div>
      <p className="border-t border-white/[0.08] px-3 py-1.5 font-mono text-[10px] text-mute">
        Shown at 2.5 Hz so it can be read. The real link streams C frames at {arm.comms.heartbeatHz} Hz against a {arm.firmware.watchdogMs} ms watchdog.
      </p>
    </div>
  );
}
