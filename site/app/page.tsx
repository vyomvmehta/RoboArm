import { ArmStage } from "@/components/ArmStage";
import { Checklist, Facts, IndexList, Section } from "@/components/ui";
import { about, building, facts, intro, joints, notYet, works } from "@/content/home";
import { loadArmConfig } from "@/lib/armConfig";
import { nav } from "@/lib/site";
import styles from "./home.module.css";

export default function Home() {
  const arm = loadArmConfig();
  const g = arm.geometry;
  const shown = facts.map((f) =>
    f.name === "Links" ? { ...f, value: `Upper arm ${g.l1} mm, forearm ${g.l2} mm, 3D printed in PLA.` } : f,
  );
  return (
    <>
      <ArmStage arm={arm} />

      <Section>
        <div className={styles.intro}>
          <div className={styles.introText}>
            {intro.map((p) => (
              <p key={p.slice(0, 24)}>{p}</p>
            ))}
          </div>
          <Facts items={shown} />
        </div>
      </Section>

      <Section title="Five joints, five motors" alt>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Joint</th>
                <th>Servo</th>
                <th>What it does</th>
              </tr>
            </thead>
            <tbody>
              {joints.map((j) => (
                <tr key={j.name}>
                  <th scope="row">{j.name}</th>
                  <td className="num">{j.servo}</td>
                  <td>{j.job}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="status" title="What works today, and what does not yet">
        <div className={styles.columns}>
          <div>
            <h3>Works</h3>
            <Checklist items={works} />
          </div>
          <div>
            <h3>Being built</h3>
            <Checklist items={building} />
          </div>
          <div>
            <h3>Not started</h3>
            <Checklist items={notYet} />
          </div>
        </div>
      </Section>

      <Section title="The rest of the story" alt>
        <IndexList items={nav.map((n) => ({ href: n.ready ? n.href : undefined, title: n.label, about: about[n.href] }))} />
      </Section>
    </>
  );
}
