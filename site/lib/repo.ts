// Build-time only. Reads the real repo (one level up from site/) so the published numbers,
// code excerpts and decision log can never drift from the arm's actual configuration.
import fs from "node:fs";
import path from "node:path";
import yaml from "js-yaml";
import { marked } from "marked";
import { ArmData, JointKey, JointSpec, Pose, ikPlanar } from "./arm";

const ROOT = path.resolve(process.cwd(), "..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const NAMES: { key: JointKey; label: string }[] = [
  { key: "j0_base", label: "J0 base" },
  { key: "j1_shoulder", label: "J1 shoulder" },
  { key: "j2_elbow", label: "J2 elbow" },
  { key: "j3_wrist", label: "J3 wrist" },
  { key: "j4_gripper", label: "J4 gripper" },
];

function must<T>(v: T | undefined | null, what: string): T {
  if (v === undefined || v === null) throw new Error(`site build: could not find ${what} in the repo`);
  return v;
}

/** `static const uint16_t NAME[...] = {a, b, ...};` or `NAME = 123;` from the sketch. */
function inoNumbers(src: string, name: string): number[] {
  const m = must(src.match(new RegExp(`${name}(?:\\[[^\\]]*\\])?\\s*=\\s*\\{?([^;]+?)\\}?;`)), name);
  return m[1].split(",").map((s) => Number(s.replace(/UL?/g, "").trim()));
}

let cached: ArmData | null = null;

export function loadArm(): ArmData {
  if (cached) return cached;
  const arm = yaml.load(read("config/arm.yaml")) as any;
  const cal = yaml.load(read("config/calibration.yaml")) as any;
  const comms = yaml.load(read("config/comms.yaml")) as any;
  const ino = read("firmware/arm_controller/arm_controller.ino");
  const servoRows = [...read("README.md").matchAll(/^\|\s*(J\d)\s+\w+\s*\|\s*(\w+)\s*\|/gm)];
  const servoOf = (i: number) => must(servoRows.find((r) => r[1] === `J${i}`), `J${i} servo in README`)[2];
  const channels = inoNumbers(ino, "CHANNEL");
  const mins = inoNumbers(ino, "PULSE_MIN");
  const maxs = inoNumbers(ino, "PULSE_MAX");

  const joints: JointSpec[] = NAMES.map(({ key, label }, i) => {
    const a = arm.joints[key];
    const c = cal.joints[key];
    const g = key === "j4_gripper";
    return {
      index: i,
      key,
      label,
      servo: servoOf(i),
      channel: channels[i],
      window: g ? null : a.window,
      limits: g ? null : a.limits,
      pulseWindow: g ? null : (c.four_bar_window ?? a.window),
      fourBar: !g && Boolean(c.four_bar_window),
      centerUs: g ? cal.center_us : (c.center_us ?? cal.center_us),
      direction: g ? 1 : c.direction,
      usPerDeg: g ? cal.joints.j3_wrist.us_per_deg : c.us_per_deg,
      minUs: g ? cal.joints.j3_wrist.min_us : c.min_us,
      maxUs: g ? cal.joints.j3_wrist.max_us : c.max_us,
      speedDegPerS: arm.speed_limits_deg_per_s[key],
    };
  });

  const data: ArmData = {
    links: {
      l1: arm.links.l1,
      l2: arm.links.l2,
      l3: arm.links.l3,
      shoulderHeight: arm.links.shoulder_height,
      shoulderOffset: arm.links.shoulder_offset,
    },
    joints,
    gripper: {
      openMm: arm.gripper.open_mm,
      closedMm: arm.gripper.closed_mm,
      openUs: cal.gripper.open_us,
      closedUs: cal.gripper.closed_us,
    },
    workspace: {
      rMin: arm.workspace.r_min,
      rMax: arm.workspace.r_max,
      zMin: arm.workspace.z_min,
      zMax: arm.workspace.z_max,
    },
    poses: {
      home: { t0: 0, t1: 0, t2: 0, t3: 0, grip: arm.gripper.open_mm },
      park: {
        t0: arm.poses.park.theta0,
        t1: arm.poses.park.theta1,
        t2: arm.poses.park.theta2,
        t3: arm.poses.park.theta3,
        grip: arm.gripper.open_mm,
      },
      homeTarget: arm.poses.home,
    },
    firmware: {
      pulseMin: Math.min(...mins),
      pulseMax: Math.max(...maxs),
      watchdogMs: inoNumbers(ino, "WATCHDOG_MS")[0],
      version: must(ino.match(/#define FW_VERSION "([^"]+)"/), "FW_VERSION")[1],
      lineMax: inoNumbers(ino, "LINE_MAX")[0],
      i2cAddr: must(ino.match(/PCA_ADDR\s*=\s*(0x[0-9A-Fa-f]+)/), "PCA_ADDR")[1],
      pwmHz: inoNumbers(ino, "PWM_FREQ_HZ")[0],
    },
    comms: { baud: comms.baud, heartbeatHz: comms.heartbeat_hz },
  };

  // The home pose is stored as a target, exactly as in arm.yaml: run IK on it here.
  const h = arm.poses.home;
  const sol = ikPlanar(data, Math.hypot(h.x, h.y), h.z, h.pitch);
  if (!sol.ok) throw new Error(`site build: home pose in config/arm.yaml is unreachable (${sol.reason})`);
  const home: Pose = { t0: 0, t1: sol.t1, t2: sol.t2, t3: sol.t3, grip: arm.gripper.open_mm };
  data.poses.home = home;
  cached = data;
  return data;
}

/** Lines of a repo file from the first line matching `start` up to (not including) `end`. */
export function excerpt(rel: string, start: RegExp, end: RegExp): { code: string; firstLine: number } {
  const lines = read(rel).split("\n");
  const a = lines.findIndex((l) => start.test(l));
  if (a < 0) throw new Error(`site build: excerpt start ${start} not found in ${rel}`);
  let b = lines.findIndex((l, i) => i > a && end.test(l));
  if (b < 0) b = lines.length;
  while (b > a && lines[b - 1].trim() === "") b--;
  return { code: lines.slice(a, b).join("\n"), firstLine: a + 1 };
}

export function testCounts() {
  const dir = path.join(ROOT, "tests");
  const files = fs.readdirSync(dir).filter((f) => /^test_.*\.py$/.test(f));
  const functions = files.reduce(
    (n, f) => n + (fs.readFileSync(path.join(dir, f), "utf8").match(/^def test_/gm)?.length ?? 0),
    0,
  );
  return { files: files.length, functions };
}

export function md(src: string): string {
  return marked.parse(src, { async: false, gfm: true }) as string;
}

/** A section file under site/content/. One file per page, one owner per file. */
export function content(name: string): string {
  return md(fs.readFileSync(path.join(process.cwd(), "content", `${name}.md`), "utf8"));
}

export interface Decision {
  id: string;
  title: string;
  date: string | null;
  meta: string;
  html: string;
  status: "decided" | "on-hold" | "superseded" | "test";
}

/** docs/DECISIONS.md -> one entry per "## Dn: ..." heading, in file order. */
export function decisions(): Decision[] {
  const src = read("docs/DECISIONS.md");
  const parts = src.split(/^## (?=D\d+:)/m).slice(1);
  return parts.map((p) => {
    const nl = p.indexOf("\n");
    const head = p.slice(0, nl).trim();
    const body = p.slice(nl + 1).replace(/^---\s*$/gm, "").trim();
    const m = must(head.match(/^(D\d+):\s*(.*)$/), `decision heading "${head}"`);
    const paren = m[2].match(/\((\d{4}-\d{2}-\d{2})[^)]*\)/);
    const title = paren ? m[2].slice(0, paren.index).trim() : m[2];
    const tail = paren ? m[2].slice(paren.index!).trim() : "";
    const status: Decision["status"] = /ON HOLD/.test(body.slice(0, 200))
      ? "on-hold"
      : /undecided|to be confirmed/i.test(head + body.slice(0, 160))
        ? "test"
        : "decided";
    return { id: m[1], title, date: paren ? paren[1] : null, meta: tail, html: md(body), status };
  });
}
