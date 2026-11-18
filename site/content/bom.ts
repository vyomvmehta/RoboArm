// Parts list for the BOM tab. Owner: Ishaan.
// Every row traces to a file in the repo. No prices: the repo does not record them per part.
export interface BomRow {
  qty: string;
  part: string;
  role: string;
  status: "in hand" | "planned" | "batch B";
  source: string;
}

export const BOM: BomRow[] = [
  { qty: "3", part: "MG996R, 180°", role: "J0 base, J1 shoulder, J2 elbow", status: "in hand", source: "docs/PINS.md s3" },
  { qty: "2", part: "MG90S", role: "J3 wrist, J4 gripper", status: "in hand", source: "docs/PINS.md s3" },
  { qty: "1", part: "Arduino Nano (CH340)", role: "Parser, safety states, watchdog", status: "in hand", source: "docs/PROTOCOL.md" },
  { qty: "1", part: "PCA9685 16-channel PWM", role: "Five servo channels over I2C", status: "in hand", source: "docs/PINS.md s2" },
  { qty: "1", part: "USB-C PD trigger", role: "Negotiates the supply voltage", status: "in hand", source: "docs/PINS.md s4" },
  { qty: "1", part: "LM2596 buck converter", role: "6.0 V servo rail", status: "in hand", source: "docs/PINS.md s4" },
  { qty: "1", part: "8 A glass fuse", role: "Short protection after the converter", status: "planned", source: "docs/DECISIONS.md D16" },
  { qty: "1", part: "Rocker kill switch", role: "Cuts the servo rail", status: "planned", source: "docs/PINS.md s4" },
  { qty: "1", part: "2200 µF capacitor", role: "Rail decoupling for servo starts", status: "planned", source: "docs/PINS.md s4" },
  { qty: "set", part: "608 bearings", role: "Base turntable carries the arm's weight", status: "in hand", source: "docs/TORQUE.md" },
  { qty: "≤ 300 g", part: "PLA printed parts", role: "Links, base enclosure, gripper", status: "batch B", source: "docs/DECISIONS.md D5" },
];
