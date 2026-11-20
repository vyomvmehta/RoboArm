// The shared building blocks. Both halves of the site build pages from these, so a page
// never needs its own colours, spacing or type sizes. /kit/ shows each one in use.
// House rules: sentence case everywhere, no labels above headings, no cards, no arrows
// on links. Structure (a number, a rule, a mark) is only used when it says something true.

import Link from "next/link";
import type { ReactNode } from "react";
import styles from "./ui.module.css";

const cx = (...c: Array<string | false | undefined>) => c.filter(Boolean).join(" ");

/** Centres content and applies the side gutter. */
export function Container({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx(styles.container, className)}>{children}</div>;
}

/** A band of the page with an optional heading. `alt` gives it the quiet tinted background. */
export function Section({ id, title, children, alt }: { id?: string; title?: string; children: ReactNode; alt?: boolean }) {
  return (
    <section id={id} className={cx(styles.section, alt && styles.alt)}>
      <Container>
        {title && <h2 className={styles.sectionTitle}>{title}</h2>}
        {children}
      </Container>
    </section>
  );
}

/** Top of every content page, on the green mat: the title and one or two sentences. */
export function PageHeader({ title, lead, children }: { title: string; lead?: ReactNode; children?: ReactNode }) {
  return (
    <header className={styles.pageHeader}>
      <Container>
        <h1>{title}</h1>
        {lead && <p className={styles.lead}>{lead}</p>}
        {children}
      </Container>
    </header>
  );
}

/** Wrap plain semantic HTML (h2, p, ul, table, pre, figure) in this and it is styled. */
export function Prose({ children }: { children: ReactNode }) {
  return <div className="prose">{children}</div>;
}

type Tone = "note" | "careful" | "wrong";
const toneTitle: Record<Tone, string> = { note: "Note", careful: "Careful", wrong: "What went wrong" };

/** An aside. `careful` is for safety; `wrong` is for the honest failures: what broke and what changed. */
export function Callout({ tone = "note", title, children }: { tone?: Tone; title?: string; children: ReactNode }) {
  return (
    <aside className={cx(styles.callout, styles[tone])}>
      <p className={styles.calloutTitle}>{title ?? toneTitle[tone]}</p>
      <div className={styles.calloutBody}>{children}</div>
    </aside>
  );
}

/** Name / value pairs, for facts and measurements. Put the unit in the value: "130 mm". */
export function Facts({ items }: { items: Array<{ name: string; value: ReactNode }> }) {
  return (
    <dl className={styles.facts}>
      {items.map((it) => (
        <div key={it.name}>
          <dt>{it.name}</dt>
          <dd>{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/** A drawing, photo or diagram with a caption. `mat` puts a drawing on the green mat. */
export function Figure({ caption, children, mat }: { caption: ReactNode; children: ReactNode; mat?: boolean }) {
  return (
    <figure className={cx(styles.figure, mat && styles.onMat)}>
      <div className={styles.figureBody}>{children}</div>
      <figcaption>{caption}</figcaption>
    </figure>
  );
}

export type State = "done" | "doing" | "todo";
const stateText: Record<State, string> = { done: "Works", doing: "Being built", todo: "Not started" };

/** A checklist of work with its honest state: a full, half or empty box, plus the word. */
export function Checklist({ items }: { items: Array<{ state: State; what: string; detail?: string }> }) {
  return (
    <ul className={styles.checklist}>
      {items.map((it) => (
        <li key={it.what}>
          <span className={cx(styles.box, styles[it.state])} aria-hidden="true" />
          <span>
            <strong>{it.what}</strong>
            <span className="visually-hidden"> ({stateText[it.state]})</span>
            {it.detail && <span className={styles.detail}>{it.detail}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A contents list: page name, one line about it. An entry without `href` is not written yet. */
export function IndexList({ items }: { items: Array<{ href?: string; title: string; about: string }> }) {
  return (
    <ul className={styles.index}>
      {items.map((it) => (
        <li key={it.title}>
          {it.href ? (
            <Link href={it.href} className={styles.indexTitle}>
              {it.title}
            </Link>
          ) : (
            <span className={cx(styles.indexTitle, styles.unwritten)}>{it.title}</span>
          )}
          <span className={styles.indexAbout}>
            {it.about}
            {!it.href && <em> Not written yet.</em>}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A link that looks like a button. Its text says what happens. */
export function ButtonLink({ href, children, quiet }: { href: string; children: ReactNode; quiet?: boolean }) {
  const cls = cx(styles.button, quiet && styles.quiet);
  return /^https?:/.test(href) ? (
    <a href={href} className={cls} rel="noopener">
      {children}
    </a>
  ) : (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}
