// Three things that went wrong. Owner: Ishaan. Each one traces to a file in the repo.
export const FAILURES = [
  {
    tag: "Parts",
    title: "The servos that could not hold an angle",
    body: "The first MG996Rs were 360° continuous-rotation units. On those, pulse width sets speed, not angle. Two of them seemed to centre near 1200 µs with no holding torque, which was correct behaviour for that part and wrong for an arm. The 180° replacements arrived on 12 November and all four were tested the next day.",
    source: "docs/PINS.md s5 · docs/DECISIONS.md D2",
  },
  {
    tag: "Wiring",
    title: "A fault the protocol cannot see",
    body: "With the LM2596's OUT− not returned to the PCA9685's ground terminal, the servo rail floats and no current flows. The driver's logic still runs from the Nano's 5 V and acknowledges every write, so the link looks perfect while the servos sit dead.",
    source: "docs/PINS.md s4",
  },
  {
    tag: "Calibration",
    title: "Microseconds per degree, off by half",
    body: "An early slope of 5.556 µs per degree understated the real figure. Sweeping every servo on the bench gave 2050 µs across 180°, which is 11.3889. The centre moved too: mid-travel is 1475 µs, not 1500.",
    source: "config/calibration.yaml (measured values)",
  },
];
