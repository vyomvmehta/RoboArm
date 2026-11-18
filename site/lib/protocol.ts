// The serial contract from docs/PROTOCOL.md, in TypeScript, so the page can run it live.
// FirmwareSim follows handle_line() in firmware/arm_controller/arm_controller.ino branch
// for branch. It is a model for explanation: the Arduino sketch is the source of truth.

export function checksum(body: string): string {
  let cs = 0;
  for (let i = 0; i < body.length; i++) cs ^= body.charCodeAt(i) & 0xff;
  return cs.toString(16).toUpperCase().padStart(2, "0");
}

export function encode(type: string, seq: number, ...fields: (string | number)[]): string {
  const body = [type, String(seq % 65536), ...fields.map(String)].join(",");
  return `${body}*${checksum(body)}`;
}

export type FwState = "DISARMED" | "ARMED" | "HOLD" | "FAULT";

export const ERROR_MEANING: Record<number, string> = {
  1: "Bad checksum. The line is ignored.",
  2: "Malformed: wrong field count, a non-number, or a line over 64 characters.",
  3: "A pulse is outside that joint's hard firmware limit. The whole frame is rejected.",
  4: "C (or H) received while not ARMED. Ignored.",
  5: "Unknown message type. Ignored.",
  6: "Watchdog fired: no valid C for 300 ms. The arm enters HOLD.",
  7: "A refused: the firmware is not in DISARMED.",
  8: "PCA9685 not found on I2C at boot. FAULT, outputs stay off.",
};

export interface FwLimits {
  pulseMin: number;
  pulseMax: number;
  lineMax: number;
  version: string;
}

export interface StepResult {
  reply: string | null;
  state: FwState;
  note: string;
  ok: boolean;
}

const isUint = (s: string, max: number) => /^\d{1,5}$/.test(s) && Number(s) <= max;

function sniffSeq(payload: string): number {
  const parts = payload.split("*")[0].split(",");
  return parts.length >= 2 && isUint(parts[1], 65535) ? Number(parts[1]) : 0;
}

export class FirmwareSim {
  state: FwState = "DISARMED";
  constructor(private lim: FwLimits) {}

  banner(): string {
    return encode("R", 0, this.lim.version, this.state);
  }

  /** The 300 ms watchdog firing: ARMED -> HOLD, with an unsolicited E,0,6. */
  watchdog(): StepResult | null {
    if (this.state !== "ARMED") return null;
    this.state = "HOLD";
    return this.err(0, 6);
  }

  private err(seq: number, code: number): StepResult {
    return { reply: encode("E", seq, code), state: this.state, note: ERROR_MEANING[code], ok: false };
  }
  private ack(seq: number, note: string): StepResult {
    return { reply: encode("K", seq, this.state), state: this.state, note, ok: true };
  }

  step(raw: string): StepResult {
    const line = raw.replace(/[\r\n]+$/, "");
    if (line.length > this.lim.lineMax) return this.err(0, 2);
    if (line.length === 0) return { reply: null, state: this.state, note: "Blank line: ignored silently.", ok: true };
    if (line.length < 4 || line[line.length - 3] !== "*") return this.err(sniffSeq(line), 2);
    const hex = line.slice(-2);
    if (!/^[0-9A-Fa-f]{2}$/.test(hex)) return this.err(sniffSeq(line), 2);
    const payload = line.slice(0, -3);
    if (checksum(payload) !== hex.toUpperCase()) return this.err(sniffSeq(payload), 1);

    const f = payload.split(",");
    if (f.length > 8) return this.err(0, 2);
    if (f[0].length !== 1) return this.err(0, 2);
    if (f.length < 2 || !isUint(f[1], 65535)) return this.err(0, 2);
    const seq = Number(f[1]);

    switch (f[0]) {
      case "C": {
        if (f.length !== 7) return this.err(seq, 2);
        if (this.state !== "ARMED" && this.state !== "HOLD") return this.err(seq, 4);
        for (const p of f.slice(2)) {
          if (!isUint(p, 65535)) return this.err(seq, 2);
          const v = Number(p);
          if (v < this.lim.pulseMin || v > this.lim.pulseMax) return this.err(seq, 3);
        }
        this.state = "ARMED";
        return this.ack(seq, "Valid frame: pulses written to the PCA9685, watchdog fed.");
      }
      case "A":
        if (f.length !== 2) return this.err(seq, 2);
        if (this.state !== "DISARMED") return this.err(seq, 7);
        this.state = "ARMED";
        return this.ack(seq, "Armed. Outputs stay off until the first C frame, so arming never jerks the arm.");
      case "D":
        if (f.length !== 2) return this.err(seq, 2);
        if (this.state !== "FAULT") this.state = "DISARMED";
        return this.ack(seq, "Disarmed: outputs off, servos limp.");
      case "H":
        if (f.length !== 2) return this.err(seq, 2);
        if (this.state !== "ARMED") return this.err(seq, 4);
        return this.ack(seq, "Home acknowledged. fw0.1 does not move on H yet; that needs the motion limiter.");
      case "P":
        if (f.length !== 2) return this.err(seq, 2);
        return this.ack(seq, "Ping: touches nothing and does not feed the watchdog.");
      default:
        return this.err(seq, 5);
    }
  }
}
