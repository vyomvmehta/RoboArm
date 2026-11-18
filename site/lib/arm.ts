// Pure arm maths shared by the build-time loader and the browser.
// Mirrors arm/kinematics/kinematics.py and arm/calibration.py. Numbers never live here:
// they come from config/arm.yaml and config/calibration.yaml through lib/repo.ts.

export type JointKey = "j0_base" | "j1_shoulder" | "j2_elbow" | "j3_wrist" | "j4_gripper";

export interface JointSpec {
  index: number;
  key: JointKey;
  label: string; // "J0 base"
  servo: string; // "MG996R"
  channel: number; // PCA9685 channel
  window: [number, number] | null; // joint degrees covered by the servo's 180 deg
  limits: [number, number] | null; // software limits, degrees
  pulseWindow: [number, number] | null; // window used for the pulse maths (four-bar for J2)
  fourBar: boolean;
  centerUs: number;
  direction: 1 | -1;
  usPerDeg: number;
  minUs: number;
  maxUs: number;
  speedDegPerS: number;
}

export interface ArmData {
  links: { l1: number; l2: number; l3: number; shoulderHeight: number; shoulderOffset: number };
  joints: JointSpec[];
  gripper: { openMm: number; closedMm: number; openUs: number; closedUs: number };
  workspace: { rMin: number; rMax: number; zMin: number; zMax: number };
  poses: { home: Pose; park: Pose; homeTarget: { x: number; y: number; z: number; pitch: number } };
  firmware: { pulseMin: number; pulseMax: number; watchdogMs: number; version: string; lineMax: number; i2cAddr: string; pwmHz: number };
  comms: { baud: number; heartbeatHz: number };
}

/** Joint angles in degrees plus the gripper opening in mm. */
export interface Pose {
  t0: number;
  t1: number;
  t2: number;
  t3: number;
  grip: number;
}

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;

export interface Chain {
  shoulder: [number, number];
  elbow: [number, number];
  wrist: [number, number];
  tip: [number, number];
  pitch: number;
}

/** Forward kinematics in the arm's vertical plane: (r, z) of each axis, in mm. */
export function chain(arm: ArmData, p: Pose): Chain {
  const { l1, l2, l3, shoulderHeight, shoulderOffset } = arm.links;
  const a1 = rad(p.t1);
  const a12 = rad(p.t1 + p.t2);
  const phi = rad(p.t1 + p.t2 + p.t3);
  const shoulder: [number, number] = [shoulderOffset, shoulderHeight];
  const elbow: [number, number] = [shoulder[0] + l1 * Math.cos(a1), shoulder[1] + l1 * Math.sin(a1)];
  const wrist: [number, number] = [elbow[0] + l2 * Math.cos(a12), elbow[1] + l2 * Math.sin(a12)];
  const tip: [number, number] = [wrist[0] + l3 * Math.cos(phi), wrist[1] + l3 * Math.sin(phi)];
  return { shoulder, elbow, wrist, tip, pitch: p.t1 + p.t2 + p.t3 };
}

export type IkResult = { ok: true; t1: number; t2: number; t3: number } | { ok: false; reason: string };

/** Planar inverse kinematics, elbow up. Port of ik() steps 2 to 4 in kinematics.py. */
export function ikPlanar(arm: ArmData, r: number, z: number, pitchDeg: number): IkResult {
  const { l1, l2, l3, shoulderHeight, shoulderOffset } = arm.links;
  const phi = rad(pitchDeg);
  const rw = r - shoulderOffset - l3 * Math.cos(phi);
  const zw = z - shoulderHeight - l3 * Math.sin(phi);
  const d = Math.hypot(rw, zw);
  if (d < 1e-9) return { ok: false, reason: "wrist point sits on the shoulder axis" };
  const cosGamma = (l1 * l1 + l2 * l2 - d * d) / (2 * l1 * l2);
  if (cosGamma < -1 || cosGamma > 1) {
    return {
      ok: false,
      reason: `wrist point is ${d.toFixed(0)} mm from the shoulder; reachable ${Math.abs(l1 - l2).toFixed(0)}-${(l1 + l2).toFixed(0)} mm`,
    };
  }
  const gamma = Math.acos(cosGamma);
  const alpha = Math.atan2(zw, rw);
  const beta = Math.acos(Math.max(-1, Math.min(1, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))));
  const t1 = deg(alpha + beta);
  const t2 = -deg(Math.PI - gamma);
  const t3 = pitchDeg - t1 - t2;
  const lim = (i: number) => arm.joints[i].limits!;
  const checks: [string, number, [number, number]][] = [
    ["shoulder", t1, lim(1)],
    ["elbow", t2, lim(2)],
    ["wrist", t3, lim(3)],
  ];
  for (const [name, v, [lo, hi]] of checks) {
    if (v < lo - 1e-6 || v > hi + 1e-6) {
      return { ok: false, reason: `${name} would need ${v.toFixed(1)} deg, limits ${lo} to ${hi}` };
    }
  }
  return { ok: true, t1, t2, t3 };
}

/** Joint angle -> pulse, same straight line as joint_to_pulse() in arm/calibration.py. */
export function jointPulse(j: JointSpec, angleDeg: number): number {
  const [lo, hi] = j.pulseWindow!;
  return Math.round(j.direction * j.usPerDeg * (angleDeg - (lo + hi) / 2) + j.centerUs);
}

/** A full pose -> the five pulse widths of a C frame. J2 uses the four-bar absolute angle. */
export function posePulses(arm: ArmData, p: Pose): number[] {
  const j = arm.joints;
  const g = arm.gripper;
  const frac = (p.grip - g.closedMm) / (g.openMm - g.closedMm);
  return [
    jointPulse(j[0], p.t0),
    jointPulse(j[1], p.t1),
    jointPulse(j[2], j[2].fourBar ? p.t1 + p.t2 : p.t2),
    jointPulse(j[3], p.t3),
    Math.round(g.closedUs + frac * (g.openUs - g.closedUs)),
  ];
}

export function inRange(arm: ArmData, pulses: number[]): boolean {
  return pulses.every((u, i) => u >= arm.joints[i].minUs && u <= arm.joints[i].maxUs);
}

// Static holding torque, using the point-mass model in docs/TORQUE.md (masses in grams,
// 30 g payload). An estimate from spec-sheet and guessed masses, not a measurement.
const STALL_KGCM = { MG996R: 9.4, MG90S: 1.8 } as const;
export const TORQUE_SOURCE = "docs/TORQUE.md point-mass model, 30 g block, stall at 4.8 V";

export function holdingTorque(arm: ArmData, p: Pose) {
  const c = chain(arm, p);
  const mid = (a: [number, number], b: [number, number], f = 0.5) => a[0] + (b[0] - a[0]) * f;
  // [mass g, horizontal position mm, first axis that carries it: 1 shoulder, 2 elbow, 3 wrist]
  const masses: [number, number, number][] = [
    [30, mid(c.shoulder, c.elbow), 1],
    [55, c.elbow[0], 1],
    [20, mid(c.elbow, c.wrist), 2],
    [15, mid(c.elbow, c.wrist, 0.3), 1],
    [13.4, c.wrist[0], 2],
    [33.4, mid(c.wrist, c.tip), 3],
    [30, c.tip[0], 3],
  ];
  const about = (axis: [number, number], level: number) =>
    Math.abs(masses.filter((m) => m[2] >= level).reduce((s, [g, x]) => s + (g / 1000) * ((x - axis[0]) / 10), 0));
  const sh = about(c.shoulder, 1);
  const el = about(c.elbow, 2);
  const wr = about(c.wrist, 3);
  return [
    { kgcm: 0, pct: 0 }, // base: the 608 bearings carry the weight
    { kgcm: sh, pct: (sh / STALL_KGCM.MG996R) * 100 },
    { kgcm: el, pct: (el / STALL_KGCM.MG996R) * 100 },
    { kgcm: wr, pct: (wr / STALL_KGCM.MG90S) * 100 },
    { kgcm: 0, pct: 0 },
  ];
}
