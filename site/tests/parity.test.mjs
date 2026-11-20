// The site's lib/kinematics.ts is a hand copy of the arm's Python. This runs both on the same
// targets with the same config/*.yaml and fails if they disagree on anything a visitor sees:
// joint angles, servo pulses, the serial frame, or the reason a target is refused.
// Run: npm test   (needs Python with the repo's requirements; set PYTHON to override the command)

import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { loadArmConfig } from "../lib/armConfig.ts";
import { frame, pulses, solve } from "../lib/kinematics.ts";

const ROOT = path.resolve(process.cwd(), "..");
const PY = process.env.PYTHON ?? (process.platform === "win32" ? "py" : "python3");

// Inside the workspace, at its edges, and refused for each reason (box, reach, joint limit).
const CASES = [
  [150, 80], [200, 30], [180, 120], [120, 60], [210, 100], [100, 40], [90, 25], [160, 200],
  [60, 80], [250, 80], [150, 10], [150, 300], [205, 240], [95, 150],
];

const PYTHON_SIDE = `
import json, sys
sys.path.insert(0, ".")
from arm.config import load_arm
from arm.calibration import load_calibration
from arm.targets import point_to_joints
from arm.comms.protocol import encode
cfg = load_arm(); cal = load_calibration(cfg)
out = []
for r, z in json.loads(sys.argv[1]):
    try:
        j = point_to_joints(cfg, r, 0, z, -90)
    except ValueError as e:
        out.append({"refused": str(e)}); continue
    try:
        p = cal.to_pulses(j + [cfg.raw["gripper"]["open_mm"]])
    except ValueError as e:
        out.append({"refused": "pulse: " + str(e)}); continue
    out.append({"angles": j[1:], "pulses": p, "frame": encode("C", 7, *p).strip()})
print(json.dumps(out))
`;

test("browser maths matches the arm's Python on the same targets", () => {
  const py = JSON.parse(execFileSync(PY, ["-c", PYTHON_SIDE, JSON.stringify(CASES)], { cwd: ROOT, encoding: "utf8" }));
  const arm = loadArmConfig();
  let solved = 0;
  CASES.forEach(([r, z], i) => {
    const ts = solve(arm, r, z);
    const want = py[i];
    const where = `target r=${r} z=${z}`;
    if (!ts.ok) {
      assert.ok(want.refused, `${where}: site refused ("${ts.why}") but the Python accepted it`);
      assert.equal(ts.why, want.refused, `${where}: refusal message differs`);
      return;
    }
    assert.ok(!want.refused, `${where}: Python refused ("${want.refused}") but the site accepted it`);
    const a = ts.angles;
    [a.theta1, a.theta2, a.theta3].forEach((v, k) => assert.ok(Math.abs(v - want.angles[k]) < 1e-3, `${where}: angle ${k + 1} ${v} vs ${want.angles[k]}`));
    const p = pulses(arm, a);
    assert.deepEqual(p, want.pulses, `${where}: pulses differ`);
    assert.equal(frame(7, p), want.frame, `${where}: serial frame differs`);
    solved++;
  });
  // A check that only ever compares refusals proves nothing about the maths.
  assert.ok(solved >= 4, `only ${solved} targets were reachable; pick cases inside this config's workspace`);
});
