import type { Metadata } from "next";
import { Callout, PageHeader, Prose, Section } from "@/components/ui";

export const metadata: Metadata = { title: "Kinematics" };

// Owner: Vyom. Outline only for now: the derivation is written by hand first, then put here.
export default function Kinematics() {
  return (
    <>
      <PageHeader
        title="From a point in space to five joint angles"
        lead="You tell the arm where the gripper should be. Inverse kinematics works out how far each joint has to turn to put it there."
      />
      <Section>
        <div style={{ display: "grid", gap: "var(--space-7)" }}>
          <Callout title="Being written">
            <p>This page is an outline. The derivation and the draggable arm come next.</p>
          </Callout>
          <Prose>
            <h2>What this page will cover</h2>
            <ol>
              <li>
                <strong>Forward first.</strong> Given the joint angles, where is the gripper? Two lines of trigonometry.
              </li>
              <li>
                <strong>Turn the base.</strong> One angle points the arm at the target and leaves a flat, two-dimensional problem.
              </li>
              <li>
                <strong>Step back from the target.</strong> Subtract the hand to find where the wrist has to be.
              </li>
              <li>
                <strong>Two links and the law of cosines.</strong> Shoulder and elbow angles, choosing the elbow-up answer.
              </li>
              <li>
                <strong>Check it.</strong> Run the answer forward again and it should land on the point you asked for.
              </li>
              <li>
                <strong>Say no.</strong> Points that are out of reach or past a joint limit are refused, not clamped.
              </li>
            </ol>
          </Prose>
        </div>
      </Section>
    </>
  );
}
