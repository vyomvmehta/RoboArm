import { Draw } from "./Reveal";
import { FwState } from "@/lib/protocol";

const O = "#FF6A1A";
const C = "#22D3EE";
const W = "rgba(243,244,246,0.7)";

function Box({ x, y, w, h, title, sub, d = 0, tone = W }: { x: number; y: number; w: number; h: number; title: string; sub?: string; d?: number; tone?: string }) {
  return (
    <g style={{ ["--d" as string]: d }}>
      <rect data-draw pathLength={1} x={x} y={y} width={w} height={h} fill="#10141A" stroke={tone} strokeWidth="1" />
      <g data-fade>
        <text x={x + w / 2} y={y + (sub ? h / 2 - 2 : h / 2 + 4)} textAnchor="middle" className="font-mono" fontSize="11" fill="#F3F4F6">
          {title}
        </text>
        {sub && (
          <text x={x + w / 2} y={y + h / 2 + 12} textAnchor="middle" className="font-mono" fontSize="8.5" fill="#8B94A3">
            {sub}
          </text>
        )}
      </g>
    </g>
  );
}
function Wire({ d, delay, color = W, dash, label, lx, ly }: { d: string; delay: number; color?: string; dash?: boolean; label?: string; lx?: number; ly?: number }) {
  return (
    <g style={{ ["--d" as string]: delay }}>
      {dash ? (
        <path data-fade d={d} fill="none" stroke={color} strokeWidth="1.2" strokeDasharray="5 4" />
      ) : (
        <path data-draw pathLength={1} d={d} fill="none" stroke={color} strokeWidth="1.4" />
      )}
      {label && (
        <text data-fade x={lx} y={ly} className="font-mono" fontSize="8.5" fill={color === W ? "#8B94A3" : color}>
          {label}
        </text>
      )}
    </g>
  );
}

/** Signal and power wiring, drawn stroke by stroke on scroll. Layout follows docs/PINS.md. */
export function WiringSchematic({ channels }: { channels: { ch: number; label: string; servo: string }[] }) {
  return (
    <Draw className="hairline overflow-x-auto bg-ink/80 p-3 sm:p-5">
      <svg viewBox="0 0 960 430" className="min-w-[720px]" role="img" aria-label="Wiring schematic: laptop to Nano over USB, Nano to PCA9685 over I2C, five servo channels, and the servo power chain with a shared ground">
        <text x="0" y="14" className="font-mono" fontSize="9" fill="#8B94A3">
          SIGNAL
        </text>
        <Box x={0} y={30} w={120} h={60} title="Laptop" sub="Python · IK" d={0} />
        <Wire d="M120 60 H190" delay={1} label="USB 115200" lx={124} ly={52} />
        <Box x={190} y={30} w={130} h={60} title="Arduino Nano" sub="5V from USB" d={1} />
        <Wire d="M320 48 H420" delay={2} color={C} label="A4 → SDA" lx={338} ly={42} />
        <Wire d="M320 72 H420" delay={2} color={C} label="A5 → SCL" lx={338} ly={88} />
        <Box x={420} y={20} w={150} h={150} title="PCA9685" sub="I2C 0x40 · 50 Hz" d={2} tone={C} />
        {channels.map((c, i) => (
          <g key={c.ch}>
            <Wire d={`M570 ${40 + i * 27} H690`} delay={3 + i * 0.5} label={`ch${c.ch}`} lx={580} ly={36 + i * 27} />
            <Box x={690} y={28 + i * 27} w={250} h={23} title={`${c.label} · ${c.servo}`} d={3 + i * 0.5} />
          </g>
        ))}

        <text x="0" y="244" className="font-mono" fontSize="9" fill="#8B94A3">
          POWER · SERVO RAIL
        </text>
        <Box x={0} y={260} w={120} h={56} title="USB-C charger" sub="Apple 96 W" d={5} />
        <Wire d="M120 288 H150" delay={6} />
        <Box x={150} y={260} w={110} h={56} title="PD trigger" sub="9 V measured" d={6} />
        <Wire d="M260 288 H290" delay={7} />
        <Box x={290} y={260} w={110} h={56} title="LM2596" sub="6.0 V" d={7} tone={O} />
        <Wire d="M400 276 H450" delay={8} />
        <Box x={450} y={260} w={76} h={32} title="Fuse 8 A" d={8} />
        <Wire d="M526 276 H546" delay={8.5} />
        <Box x={546} y={260} w={76} h={32} title="Switch" d={8.5} />
        <Wire d="M622 276 H642" delay={9} />
        <Box x={642} y={260} w={84} h={32} title="2200 µF" d={9} />
        <text data-fade style={{ ["--d" as string]: 9 }} x={450} y={306} className="font-mono" fontSize="8.5" fill={O}>
          planned, not installed yet
        </text>
        <Wire d="M726 276 H780 V200 H520 V170" delay={10} color={O} label="V+ 6.0 V → screw terminal" lx={610} ly={194} />

        {/* the ground net */}
        <Wire d="M345 316 V360 H432 V170" delay={11} color={O} label="OUT− → PCA9685 GND terminal (the return path)" lx={444} ly={356} />
        <Wire d="M275 90 V400 H432 V360" delay={12} color={O} label="Nano GND: one common ground net" lx={286} ly={416} />
      </svg>
    </Draw>
  );
}

/** PROTOCOL.md section 6 as a diagram. `current` lights the state the simulated firmware is in. */
export function StateDiagram({ current }: { current: FwState }) {
  const node = (id: FwState, x: number, y: number) => {
    const on = current === id;
    return (
      <g>
        <rect x={x - 62} y={y - 20} width="124" height="40" fill={on ? "rgba(255,106,26,0.12)" : "#10141A"} stroke={on ? O : W} strokeWidth={on ? 1.6 : 1} style={{ transition: "all .3s" }} />
        <text x={x} y={y + 4} textAnchor="middle" className="font-mono" fontSize="11" fill={on ? O : "#F3F4F6"}>
          {id}
        </text>
      </g>
    );
  };
  const edge = (d: string, label: string, lx: number, ly: number) => (
    <g>
      <path d={d} fill="none" stroke={W} strokeWidth="1" markerEnd="url(#arrow)" />
      <text x={lx} y={ly} textAnchor="middle" className="font-mono" fontSize="9" fill="#8B94A3">
        {label}
      </text>
    </g>
  );
  return (
    <svg viewBox="0 0 560 210" className="w-full" role="img" aria-label={`Firmware state machine. Current state: ${current}`}>
      <defs>
        <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 L8 4 L0 8 z" fill={W} />
        </marker>
      </defs>
      {edge("M10 50 H36", "reset", 22, 40)}
      {edge("M162 42 H216", "A", 189, 34)}
      {edge("M216 58 H162", "D", 189, 74)}
      {edge("M342 42 H434", "no C for 300 ms", 388, 34)}
      {edge("M434 58 H342", "valid C", 388, 74)}
      {edge("M500 70 C 500 130, 300 120, 128 72", "D", 420, 122)}
      {edge("M280 70 V150", "", 0, 0)}
      {edge("M100 70 C 100 150, 150 170, 216 170", "PCA9685 missing", 110, 188)}
      {node("DISARMED", 100, 50)}
      {node("ARMED", 280, 50)}
      {node("HOLD", 498, 50)}
      {node("FAULT", 280, 170)}
      <text x="352" y="174" className="font-mono" fontSize="9" fill="#8B94A3">
        outputs off until reset
      </text>
    </svg>
  );
}
