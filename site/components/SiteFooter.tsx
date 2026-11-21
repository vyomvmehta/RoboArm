import Link from "next/link";
import { nav, site } from "@/lib/site";
import styles from "./SiteFooter.module.css";

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <p className={styles.credit}>
          Built by {site.team.slice(0, -1).join(", ")} and {site.team.at(-1)} at the {site.school}, 2026.
        </p>
        <p>
          We used Claude, an AI assistant, as a tutor and pair programmer.{" "}
          <a href={`${site.repoUrl}#how-we-built-this`} rel="noopener">
            Read how we built this
          </a>
          .
        </p>
        <nav aria-label="Footer">
          <ul className={styles.links}>
            <li>
              <Link href="/">Home</Link>
            </li>
            {nav
              .filter((n) => n.ready)
              .map((n) => (
                <li key={n.href}>
                  <Link href={n.href}>{n.label}</Link>
                </li>
              ))}
            <li>
              <a href={site.repoUrl} rel="noopener">
                Code on GitHub
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </footer>
  );
}
