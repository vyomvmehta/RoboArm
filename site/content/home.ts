// Home page copy. Owner: Vyom. (Moves to Markdown once the content loader lands.)
// Rule for this file: only say what is true today. Update the checklists as work lands.

import type { State } from "@/components/ui";

export const intro = [
  "RoboArm is a desktop robot arm that three of us at the University of Waterloo designed in SolidWorks and are 3D printing and programming ourselves: Vyom Mehta, Ishaan and Siddharth.",
  "You drive it from a web page. Give it a point and it works out how far each joint has to turn, the way the demo above does, or move one joint at a time with a slider. Hand-gesture control comes after this version works.",
  "It is not finished. The maths, the messages and the control page work today. The arm itself is being printed and assembled.",
];

export const facts = [
  { name: "Motors", value: "Five hobby servos: three MG996R for the base, shoulder and elbow, two MG90S for the wrist and gripper." },
  { name: "Links", value: "" }, // filled from config/arm.yaml by app/page.tsx
  { name: "Elbow", value: "Driven through a four-bar linkage, so its motor sits down at the shoulder instead of riding on the arm." },
  { name: "Control", value: "Python on a laptop, an Arduino Nano and a PCA9685 servo driver." },
  { name: "Messages", value: "30 a second over USB, each with a checksum. About 12 ms there and back, measured on the bench." },
];

export const joints = [
  { name: "Base", servo: "MG996R", job: "Turns the whole arm left and right" },
  { name: "Shoulder", servo: "MG996R", job: "Raises and lowers the upper arm" },
  { name: "Elbow", servo: "MG996R", job: "Sets the forearm's angle through the four-bar rod" },
  { name: "Wrist", servo: "MG90S", job: "Sets the gripper's angle, for example straight down to pick something up" },
  { name: "Gripper", servo: "MG90S", job: "Opens and closes the jaws" },
];

type Item = { state: State; what: string; detail?: string };

export const works: Item[] = [
  { state: "done", what: "Inverse kinematics", detail: "Derived by hand, then coded in Python with unit tests." },
  { state: "done", what: "Laptop-to-Arduino messages", detail: "Lines of text with a checksum, tested with the same cases on both ends." },
  { state: "done", what: "Firmware, first version", detail: "Reads commands, starts disarmed, holds still if the laptop stops talking." },
  { state: "done", what: "Control web page", detail: "Sliders tested on one real servo. Go-to-a-point tested against a simulated Arduino so far." },
];

export const building: Item[] = [
  { state: "doing", what: "CAD", detail: "Arm links and gripper are drawn in SolidWorks. The base is in review." },
  { state: "doing", what: "Firmware speed limiter", detail: "Written and in review." },
];

export const notYet: Item[] = [
  { state: "todo", what: "Print, assemble, wire, calibrate", detail: "Nothing on this site is measured on the full arm yet." },
  { state: "todo", what: "The page drives the real arm", detail: "Aiming for late November 2026." },
  { state: "todo", what: "Hand-gesture control", detail: "January 2027." },
];

export const about: Record<string, string> = {
  "/mechanical/": "The four-bar elbow, the torque sums that sized the arm, and how the parts were drawn to print.",
  "/kinematics/": "From a point in space to joint angles, with the derivation.",
  "/electronics/": "The power path, the servo driver and the wiring.",
  "/software/": "The messages, the firmware's safe states, the speed limiter and how it is tested.",
  "/build-log/": "Every decision in order, including the ones that turned out wrong.",
};
