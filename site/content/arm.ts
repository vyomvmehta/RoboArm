// The arm's numbers, copied by hand from config/arm.yaml and config/calibration.yaml.
// TEMPORARY: replace with the content loader's build-time read of those files, so the
// site cannot drift from the arm. Until then, change a number here only when it changes there.
//
// Source: arm.yaml as of 2026-11-16 (130 / 120 / 84 mm links on Siddharth's 174.5 mm base),
// calibration.yaml on main (every servo 450-2500 us over 180 deg, mid-travel 1475 us).

export const geometry = {
  l1: 130, // shoulder axis -> elbow axis, mm
  l2: 120, // elbow axis -> wrist axis, mm
  l3: 84, // wrist axis -> grasp point, mm
  shoulderHeight: 174.5, // shoulder axis above the table, mm
  shoulderOffset: 0,
  fourBarCrank: 30, // crank = lever, mm
};

/** Software joint limits, degrees. */
export const limits = {
  theta1: [-20, 140],
  theta2: [-135, 0],
  theta3: [-95, 50],
} as const;

/** Targets outside this box are refused before any maths is done. */
export const workspace = { rMin: 140, rMax: 230, zMin: 25, zMax: 250 };

/** Top speed per joint, degrees per second. */
export const speed = { theta1: 45, theta2: 45, theta3: 90 };

export const heartbeatHz = 30;

/** Joint angle -> pulse. `centreDeg` is the joint angle the horn was fitted at (1475 us). */
export const servo = {
  centreUs: 1475,
  usPerDeg: 11.3889,
  minUs: 500,
  maxUs: 2450,
  base: { centreDeg: 0, direction: 1 },
  shoulder: { centreDeg: 60, direction: 1 },
  // Four-bar: the elbow servo holds the forearm's angle to the horizontal, theta1 + theta2.
  elbow: { centreDeg: -10, direction: -1 },
  wrist: { centreDeg: -30, direction: 1 },
  gripperOpenUs: 1665,
};

export const home = { r: 150, z: 80 };
