import type { Metadata } from "next";
import { Callout, PageHeader, Prose, Section } from "@/components/ui";

export const metadata: Metadata = { title: "Mechanical" };

// Owner: Vyom. Outline only for now: the headings are the plan for this page.
export default function Mechanical() {
  return (
    <>
      <PageHeader
        title="Designing an arm that a hobby servo can hold up"
        lead="Why the elbow motor sits at the shoulder, how the link lengths were chosen, and how the parts were drawn so they print and bolt together."
      />
      <Section>
        <div style={{ display: "grid", gap: "var(--space-7)" }}>
          <Callout title="Being written">
            <p>This page is an outline. Renders, torque numbers and print settings go in once the arm is printed and the numbers are final.</p>
          </Callout>
          <Prose>
            <h2>What this page will cover</h2>
            <ul>
              <li>
                <strong>The four-bar elbow.</strong> Both big motors sit on the turntable. A crank and a rod carry the elbow motor's
                motion up to the forearm, so that motor sets the forearm's angle to the ground, not the bend at the elbow.
              </li>
              <li>
                <strong>Sizing the arm.</strong> The torque sums at the shoulder for the worst case, arm stretched flat, and how they
                led to 130 and 120 mm links.
              </li>
              <li>
                <strong>Designing for a 3D printer.</strong> The test prints that set every hole, nut pocket and bearing seat, and why
                one global tolerance would have been wrong.
              </li>
              <li>
                <strong>The gripper.</strong> One servo, a pinion and two racks.
              </li>
              <li>
                <strong>CAD by script.</strong> The SolidWorks parts are generated from Python, with an interference check at every pose.
              </li>
            </ul>
          </Prose>
        </div>
      </Section>
    </>
  );
}
