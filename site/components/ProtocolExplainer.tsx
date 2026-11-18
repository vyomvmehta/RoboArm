"use client";
import { useMemo, useRef, useState } from "react";
import { CornerDownLeft, RotateCcw, Timer, Wand2 } from "lucide-react";
import { FirmwareSim, FwLimits, FwState, StepResult, checksum, encode } from "@/lib/protocol";
import MagneticButton from "./MagneticButton";
import { StateDiagram } from "./Diagrams";

interface LogLine {
  id: number;
  dir: ">" | "<" | "·";
  text: string;
  note?: string;
  bad?: boolean;
}

/**
 * Type a command frame, watch the XOR checksum compute byte by byte, and see what the
 * firmware would reply. The parser is a TypeScript model of handle_line() in the sketch.
 */
export default function ProtocolExplainer({ limits }: { limits: FwLimits }) {
  const presets = useMemo(
    () => [
      { label: "Arm", line: encode("A", 3) },
      { label: "Pose", line: encode("C", 4, 1100, 1620, 1480, 1500, 2000) },
      { label: "Ping", line: encode("P", 5) },
      { label: "Bad checksum", line: "C,6,1500,1500,1500,1500,1500*00" },
      { label: "Pulse too wide", line: encode("C", 7, 1500, 1500, limits.pulseMax + 500, 1500, 1500) },
      { label: "Unknown type", line: encode("Z", 8) },
      { label: "Disarm", line: encode("D", 9) },
    ],
    [limits.pulseMax],
  );
  const sim = useRef<FirmwareSim | null>(null);
  if (!sim.current) sim.current = new FirmwareSim(limits);
  const nextId = useRef(1);
  const [line, setLine] = useState(presets[0].line);
  const [state, setState] = useState<FwState>("DISARMED");
  const [last, setLast] = useState<StepResult | null>(null);
  const [log, setLog] = useState<LogLine[]>(() => [{ id: 0, dir: "<", text: encode("R", 0, limits.version, "DISARMED"), note: "Boot banner" }]);

  const star = line.lastIndexOf("*");
  const payload = star >= 0 ? line.slice(0, star) : line;
  const given = star >= 0 ? line.slice(star + 1) : "";
  const want = checksum(payload);
  const match = given.toUpperCase() === want;
  const running = useMemo(() => {
    let cs = 0;
    return payload.split("").map((ch) => {
      cs ^= ch.charCodeAt(0) & 0xff;
      return { ch, hex: (ch.charCodeAt(0) & 0xff).toString(16).toUpperCase().padStart(2, "0"), run: cs.toString(16).toUpperCase().padStart(2, "0") };
    });
  }, [payload]);

  const add = (...l: Omit<LogLine, "id">[]) => setLog((p) => [...p, ...l.map((x) => ({ ...x, id: nextId.current++ }))].slice(-14));
  const record = (res: StepResult, sent?: string) => {
    setLast(res);
    setState(res.state);
    add(...(sent ? [{ dir: ">" as const, text: sent }] : []), { dir: "<", text: res.reply ?? "(no reply)", note: res.note, bad: !res.ok });
  };
  const send = () => record(sim.current!.step(line), line);
  const wait = () => {
    const res = sim.current!.watchdog();
    if (res) record(res);
    else add({ dir: "·", text: "300 ms pass. Nothing happens: the watchdog only runs while ARMED." });
  };
  const reset = () => {
    sim.current = new FirmwareSim(limits);
    setState("DISARMED");
    setLast(null);
    add({ dir: "·", text: "Board reset (opening the port does this)." }, { dir: "<", text: sim.current.banner(), note: "Boot banner" });
  };

  return (
    <div className="grid gap-px bg-white/[0.08] lg:grid-cols-2">
      <div className="min-w-0 space-y-5 bg-ink p-4 sm:p-6">
        <div>
          <label htmlFor="frame" className="label">
            Command frame · &lt;TYPE&gt;,&lt;seq&gt;[,fields]*&lt;CS&gt;
          </label>
          <div className="mt-2 flex gap-2">
            <input
              id="frame"
              value={line}
              onChange={(e) => setLine(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              spellCheck={false}
              autoComplete="off"
              className="hairline min-w-0 flex-1 bg-black/50 px-3 py-2.5 font-mono text-sm text-paper outline-none focus:border-scope/60"
            />
            <MagneticButton onClick={send} active aria-label="Send frame to the simulated firmware">
              <CornerDownLeft size={13} /> Send
            </MagneticButton>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {presets.map((p) => (
              <button key={p.label} onClick={() => setLine(p.line)} className="hairline press px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-mute transition-colors hover:text-paper">
                {p.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <span className="label">XOR of every byte before the *</span>
            <span className={`font-mono text-xs ${match ? "text-scope" : "text-red-400"}`}>
              computed {want} · {given ? `given ${given}` : "none given"} · {match ? "match" : "mismatch"}
            </span>
          </div>
          <div className="mt-2 flex max-h-40 flex-wrap gap-px overflow-y-auto bg-white/[0.06] p-px font-mono text-[10px]">
            {running.map((b, i) => (
              <div key={i} className="flex w-9 flex-col items-center bg-ink py-1">
                <span className="text-paper">{b.ch === " " ? "␠" : b.ch}</span>
                <span className="text-mute">{b.hex}</span>
                <span className={i === running.length - 1 ? "text-signal" : "text-scope/70"}>{b.run}</span>
              </div>
            ))}
            {running.length === 0 && <div className="bg-ink px-3 py-2 text-mute">Type a frame to see the checksum build up.</div>}
          </div>
          <p className="mt-2 font-mono text-[10px] text-mute">Rows: character, its byte in hex, the running XOR. The last running value is the checksum.</p>
          {!match && (
            <button onClick={() => setLine(`${payload}*${want}`)} className="mt-2 inline-flex items-center gap-1.5 font-mono text-[11px] text-scope hover:underline">
              <Wand2 size={12} /> fix the checksum
            </button>
          )}
        </div>

        <div className="flex flex-wrap gap-2">
          <MagneticButton onClick={wait}>
            <Timer size={13} /> Let 300 ms pass
          </MagneticButton>
          <MagneticButton onClick={reset}>
            <RotateCcw size={13} /> Reset board
          </MagneticButton>
        </div>
      </div>

      <div className="min-w-0 space-y-4 bg-ink p-4 sm:p-6">
        <div className="flex items-center justify-between">
          <span className="label">Firmware state</span>
          <span className="font-mono text-xs text-signal">{state}</span>
        </div>
        <StateDiagram current={state} />
        <div className="hairline min-h-[4.5rem] bg-black/40 p-3" aria-live="polite">
          {last ? (
            <>
              <div className={`font-mono text-sm ${last.ok ? "text-scope" : "text-red-400"}`}>{last.reply ?? "(no reply)"}</div>
              <p className="mt-1 text-sm text-paper/70">{last.note}</p>
            </>
          ) : (
            <p className="text-sm text-paper/60">Send a frame. Try a pose before arming, or arm and then let 300 ms pass.</p>
          )}
        </div>
        <div className="h-40 overflow-y-auto font-mono text-[11px] leading-[1.7]">
          {log.map((l) => (
            <div key={l.id} className={l.dir === "·" ? "text-mute" : l.bad ? "text-red-400" : l.dir === ">" ? "text-paper/85" : "text-scope"}>
              <span className="mr-2 select-none text-white/30">{l.dir}</span>
              {l.text}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
