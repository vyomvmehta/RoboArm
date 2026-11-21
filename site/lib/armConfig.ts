// Build-time only: reads the arm's numbers from the repo's own config files, so the site can
// never describe a different arm from the one the code drives (Ishaan's review of #19).
// When #17 lands, this can become a thin adapter over its loadArm() in lib/repo.ts.
//
//   config/arm.yaml          links, limits, windows, workspace, speeds, home pose, four-bar crank, base clearance
//   config/calibration.yaml  centre pulse, direction, us/deg, pulse range, four-bar window, gripper
//   config/comms.yaml        heartbeat rate

import fs from "node:fs";
import path from "node:path";
import yaml from "js-yaml";
import type { ArmConfig, ServoJoint } from "./kinematics.ts";

const ROOT = path.resolve(process.cwd(), "..");
const read = (rel: string) => yaml.load(fs.readFileSync(path.join(ROOT, rel), "utf8")) as any;

const centre = (w: [number, number]) => (w[0] + w[1]) / 2;

export function loadArmConfig(): ArmConfig {
  const arm = read("config/arm.yaml");
  const cal = read("config/calibration.yaml");
  const comms = read("config/comms.yaml");
  const J = arm.joints;
  const C = cal.joints;

  // The horn goes on with the joint at its window centre (arm.yaml note), so that angle is the
  // one that maps to the centre pulse. The four-bar elbow uses its own window (calibration.yaml).
  const joint = (key: string, window: [number, number]): ServoJoint => ({
    centreDeg: centre(window),
    direction: C[key].direction,
    centreUs: C[key].center_us ?? cal.center_us,
    usPerDeg: C[key].us_per_deg,
    minUs: C[key].min_us,
    maxUs: C[key].max_us,
  });

  const bc = arm.base_clearance;
  if (!bc) throw new Error("site build: config/arm.yaml has no base_clearance (D23)");

  const fourBar = arm.four_bar;
  if (!fourBar?.crank_mm) throw new Error("site build: config/arm.yaml has no four_bar.crank_mm");

  return {
    geometry: {
      l1: arm.links.l1,
      l2: arm.links.l2,
      l3: arm.links.l3,
      shoulderHeight: arm.links.shoulder_height,
      shoulderOffset: arm.links.shoulder_offset,
      fourBarCrank: fourBar.crank_mm,
    },
    limits: { theta1: J.j1_shoulder.limits, theta2: J.j2_elbow.limits, theta3: J.j3_wrist.limits },
    workspace: { rMin: arm.workspace.r_min, rMax: arm.workspace.r_max, zMin: arm.workspace.z_min, zMax: arm.workspace.z_max },
    speed: {
      theta1: arm.speed_limits_deg_per_s.j1_shoulder,
      theta2: arm.speed_limits_deg_per_s.j2_elbow,
      theta3: arm.speed_limits_deg_per_s.j3_wrist,
    },
    heartbeatHz: comms.heartbeat_hz,
    servo: {
      base: joint("j0_base", J.j0_base.window),
      shoulder: joint("j1_shoulder", J.j1_shoulder.window),
      elbow: joint("j2_elbow", C.j2_elbow.four_bar_window ?? J.j2_elbow.window),
      fourBarElbow: Boolean(C.j2_elbow.four_bar_window),
      wrist: joint("j3_wrist", J.j3_wrist.window),
      gripperOpenUs: cal.gripper.open_us,
    },
    home: { r: Math.hypot(arm.poses.home.x, arm.poses.home.y), z: arm.poses.home.z },
    clearance: {
      lidBelowShoulder: bc.lid_below_shoulder,
      boxHalf: bc.box_half,
      plateR: bc.plate_r,
      plateTopBelowShoulder: bc.plate_top_below_shoulder,
      forearmHalfWidth: bc.forearm_half_width,
      handOriginFromWrist: bc.hand_origin_from_wrist,
      handBody: bc.hand_body,
      handFingers: bc.hand_fingers,
      margin: bc.margin,
    },
  };
}
