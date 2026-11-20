// A browser copy of the arm's own maths, kept line-for-line with the Python it mirrors:
//   arm/kinematics/kinematics.py  ik()            (derived by hand first, then coded)
//   arm/targets.py                point_to_joints (workspace box, then IK, then limits)
//   arm/calibration.py            joint_to_pulse  (angle -> pulse, refuse rather than clamp)
//   arm/comms/protocol.py         encode          (XOR checksum, as two hex digits)
//   arm/motion.py + control.py    step_toward     (all joints arrive together) + four-bar cap
// Side view only: the base angle is 0 and the gripper points straight down (pitch -90).
// Every number comes in through `cfg`, read from config/*.yaml at build time (lib/armConfig.ts).
// tests/parity.test.mjs checks this file against the Python on the same targets.

const RAD = Math.PI / 180;

export type ServoJoint = { centreDeg: number; direction: number; centreUs: number; usPerDeg: number; minUs: number; maxUs: number };

export type ArmConfig = {
  geometry: { l1: number; l2: number; l3: number; shoulderHeight: number; shoulderOffset: number; fourBarCrank: number };
  limits: { theta1: [number, number]; theta2: [number, number]; theta3: [number, number] };
  workspace: { rMin: number; rMax: number; zMin: number; zMax: number };
  speed: { theta1: number; theta2: number; theta3: number };
  heartbeatHz: number;
  servo: { base: ServoJoint; shoulder: ServoJoint; elbow: ServoJoint; fourBarElbow: boolean; wrist: ServoJoint; gripperOpenUs: number };
  home: { r: number; z: number };
};

export type Angles = { theta1: number; theta2: number; theta3: number }; // degrees
export type Solve = { ok: true; angles: Angles } | { ok: false; why: string };

const f1 = (v: number) => v.toFixed(1);

/** Target (mm out from the base axis, mm above the table) -> joint angles, or the reason it is refused. */
export function solve(cfg: ArmConfig, r: number, z: number): Solve {
  const { geometry: g, workspace: ws, limits } = cfg;
  if (!(ws.rMin <= r && r <= ws.rMax)) {
    return { ok: false, why: `${r.toFixed(0)} mm from the base axis is outside the workspace (${ws.rMin}-${ws.rMax} mm)` };
  }
  if (!(ws.zMin <= z && z <= ws.zMax)) {
    return { ok: false, why: `z = ${z.toFixed(0)} mm is outside the workspace (${ws.zMin}-${ws.zMax} mm)` };
  }
  const phi = -90 * RAD;
  // Step back from the grasp point along the gripper to find the wrist axis.
  const rw = r - g.shoulderOffset - g.l3 * Math.cos(phi);
  const zw = z - g.shoulderHeight - g.l3 * Math.sin(phi);

  // Two links and the law of cosines.
  const d = Math.hypot(rw, zw);
  const cosGamma = (g.l1 ** 2 + g.l2 ** 2 - d ** 2) / (2 * g.l1 * g.l2);
  if (d < 1e-9 || cosGamma < -1 - 1e-9 || cosGamma > 1 + 1e-9) {
    return {
      ok: false,
      why: `wrist point is ${f1(d)} mm from the shoulder; reachable range is ${f1(Math.abs(g.l1 - g.l2))}-${f1(g.l1 + g.l2)} mm`,
    };
  }
  const gamma = Math.acos(Math.max(-1, Math.min(1, cosGamma)));
  const alpha = Math.atan2(zw, rw);
  const beta = Math.acos(Math.max(-1, Math.min(1, (g.l1 ** 2 + d ** 2 - g.l2 ** 2) / (2 * g.l1 * d))));

  const theta1 = (alpha + beta) / RAD; // elbow-up
  const theta2 = -(Math.PI - gamma) / RAD;
  const theta3 = -90 - theta1 - theta2;
  const angles = { theta1, theta2, theta3 };

  for (const name of ["theta1", "theta2", "theta3"] as const) {
    const [lo, hi] = limits[name];
    if (angles[name] < lo - 1e-7 || angles[name] > hi + 1e-7) {
      return { ok: false, why: `${name} = ${f1(angles[name])} deg is outside [${f1(lo)}, ${f1(hi)}] deg` };
    }
  }
  return { ok: true, angles };
}

/** Joint positions in the side view, mm, table at z = 0. */
export function fk(cfg: ArmConfig, a: Angles) {
  const g = cfg.geometry;
  const a1 = a.theta1 * RAD;
  const a12 = (a.theta1 + a.theta2) * RAD;
  const phi = (a.theta1 + a.theta2 + a.theta3) * RAD;
  const S = { x: g.shoulderOffset, z: g.shoulderHeight };
  const E = { x: S.x + g.l1 * Math.cos(a1), z: S.z + g.l1 * Math.sin(a1) };
  const W = { x: E.x + g.l2 * Math.cos(a12), z: E.z + g.l2 * Math.sin(a12) };
  const T = { x: W.x + g.l3 * Math.cos(phi), z: W.z + g.l3 * Math.sin(phi) };
  // Four-bar: the crank at the shoulder and the lever behind the elbow both point back along the forearm.
  const C = { x: S.x - g.fourBarCrank * Math.cos(a12), z: S.z - g.fourBarCrank * Math.sin(a12) };
  const L = { x: E.x - g.fourBarCrank * Math.cos(a12), z: E.z - g.fourBarCrank * Math.sin(a12) };
  return { S, E, W, T, C, L, phi };
}

function pulse(deg: number, j: ServoJoint): number {
  return Math.round(j.direction * j.usPerDeg * (deg - j.centreDeg) + j.centreUs);
}

/** The five pulses, in microseconds, that hold this pose: base, shoulder, elbow, wrist, gripper. */
export function pulses(cfg: ArmConfig, a: Angles): number[] {
  const s = cfg.servo;
  return [
    pulse(0, s.base),
    pulse(a.theta1, s.shoulder),
    // Four-bar: the elbow servo holds the forearm's angle to the horizontal, theta1 + theta2.
    pulse(s.fourBarElbow ? a.theta1 + a.theta2 : a.theta2, s.elbow),
    pulse(a.theta3, s.wrist),
    s.gripperOpenUs,
  ];
}

export function pulsesInRange(cfg: ArmConfig, p: number[]): boolean {
  const s = cfg.servo;
  return [s.base, s.shoulder, s.elbow, s.wrist].every((j, i) => j.minUs <= p[i] && p[i] <= j.maxUs);
}

export function checksum(body: string): string {
  let cs = 0;
  for (let i = 0; i < body.length; i++) cs ^= body.charCodeAt(i);
  return cs.toString(16).toUpperCase().padStart(2, "0");
}

/** The text line the laptop sends: C,<seq>,<five pulses>*<checksum>. */
export function frame(seq: number, p: number[]): string {
  const body = ["C", String(seq % 65536), ...p.map(String)].join(",");
  return `${body}*${checksum(body)}`;
}

/** One tick of the laptop's ramp: every joint covers the same fraction of its trip, so they arrive together. */
export function stepToward(cfg: ArmConfig, cur: Angles, goal: Angles): Angles {
  const dt = 1 / cfg.heartbeatHz;
  const speed = cfg.speed;
  const names = ["theta1", "theta2", "theta3"] as const;
  const ticks = Math.max(...names.map((n) => Math.abs(goal[n] - cur[n]) / (speed[n] * dt)));
  if (ticks <= 1) return { ...goal };
  const next = { ...cur };
  for (const n of names) next[n] = cur[n] + (goal[n] - cur[n]) / ticks;

  // Four-bar: the elbow servo turns by d(theta1) + d(theta2). Keep that inside its own speed.
  // A speed of 0 or less means "frozen" (same rule as the Python): leave the step alone.
  const cap = speed.theta2 * dt;
  if (cfg.servo.fourBarElbow && cap > 0) {
    const servoMove = Math.abs(next.theta1 - cur.theta1 + (next.theta2 - cur.theta2));
    if (servoMove > cap + 1e-9) {
      const f = cap / servoMove;
      for (const n of names) next[n] = cur[n] + (next[n] - cur[n]) * f;
    }
  }
  return next;
}
