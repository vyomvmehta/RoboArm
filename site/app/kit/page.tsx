import type { Metadata } from "next";
import { ButtonLink, Callout, Checklist, Facts, Figure, IndexList, PageHeader, Prose, Section } from "@/components/ui";

export const metadata: Metadata = { title: "Kit", robots: { index: false } };

// Not in the nav. Every shared building block in one place, so both halves of the site
// can see what exists before writing a page. Import from "@/components/ui".
export default function Kit() {
  return (
    <>
      <PageHeader
        title="The kit"
        lead="Every building block the pages are made from. If a page needs something that is not here, add it here first so both halves can use it."
      />

      <Section title="Page structure">
        <Prose>
          <p>
            A page starts with a <code>PageHeader</code> (title and lead, on the green mat) and is then a stack of{" "}
            <code>Section</code>s. A section takes an optional <code>title</code>, and <code>alt</code> for the tinted band.
          </p>
          <p>
            House style: sentence case, no small label above a heading, no cards, no arrows on links. Number things only when
            they are a real sequence. Yellow means the target or a live value and red means refused; nothing else uses them.
          </p>
        </Prose>
      </Section>

      <Section title="Plain HTML, styled" alt>
        <Prose>
          <p>
            Wrap ordinary HTML in <code>Prose</code>. Headings, paragraphs, lists, tables, code and quotes pick up the look with
            no class names, so content can be written before any design exists.
          </p>
          <h3>A third-level heading</h3>
          <ul>
            <li>
              A measured value gets <code>className="num"</code> and its unit: <span className="num">1475 µs</span>.
            </li>
            <li>
              A <a href="#">link</a> and some <strong>strong text</strong>.
            </li>
          </ul>
          <pre>
            <code>{"C,2,1100,1620,1480,1500,2000*7F\nK,2,ARMED*26"}</code>
          </pre>
          <blockquote>
            <p>A quote, for example a line from the decision log.</p>
          </blockquote>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Meaning</th>
                  <th>Firmware does</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="num">1</td>
                  <td>Bad checksum</td>
                  <td>Ignores the line</td>
                </tr>
                <tr>
                  <td className="num">3</td>
                  <td>A pulse is outside the joint's hard limit</td>
                  <td>Rejects the whole frame</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Prose>
      </Section>

      <Section title="Asides">
        <div style={{ display: "grid", gap: "var(--space-6)" }}>
          <Callout>
            <p>
              The default tone, <code>note</code>: useful, but not part of the main line.
            </p>
          </Callout>
          <Callout tone="careful">
            <p>
              <code>careful</code> is for safety: things that pinch, burn or back-feed.
            </p>
          </Callout>
          <Callout tone="wrong">
            <p>
              <code>wrong</code> is for the honest failures. Say what broke, how we found it and what changed.
            </p>
          </Callout>
        </div>
      </Section>

      <Section title="Facts and measurements" alt>
        <Facts
          items={[
            { name: "Pulse range", value: <span className="num">450 to 2500 µs</span> },
            { name: "Scale", value: <span className="num">11.39 µs per degree</span> },
            { name: "Mid-travel", value: <span className="num">1475 µs, measured on every servo</span> },
          ]}
        />
      </Section>

      <Section title="State of the work">
        <Checklist
          items={[
            { state: "done", what: "A full box works", detail: "Say how it was tested." },
            { state: "doing", what: "A half box is being built", detail: "Say what is left." },
            { state: "todo", what: "An empty box is not started" },
          ]}
        />
      </Section>

      <Section title="Figures" alt>
        <div style={{ display: "grid", gap: "var(--space-6)", maxWidth: "44rem" }}>
          <Figure mat caption="With mat, a drawing sits on the green mat. Draw in chalk (var(--chalk)); keep yellow for a target or a live value.">
            <svg viewBox="0 0 300 90" role="img" aria-label="Placeholder drawing">
              <path d="M20 70 L110 25 L220 45 L280 20" fill="none" stroke="var(--chalk)" strokeWidth="2.5" strokeLinecap="round" />
              <circle cx="110" cy="25" r="5" fill="var(--chalk)" />
            </svg>
          </Figure>
          <Figure caption="Without it, the figure is plain: use this for photos and renders.">
            <div style={{ height: "8rem", background: "var(--line)" }} />
          </Figure>
        </div>
      </Section>

      <Section title="Links to other pages">
        <IndexList
          items={[
            { href: "/", title: "A page", about: "One line about what is on it." },
            { title: "Another page", about: "Without an href it shows as not written yet." },
          ]}
        />
        <p style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap", marginTop: "var(--space-6)" }}>
          <ButtonLink href="/">Go to the home page</ButtonLink>
          <ButtonLink href="/" quiet>
            A quieter button
          </ButtonLink>
        </p>
      </Section>
    </>
  );
}
