"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { nav, site } from "@/lib/site";
import styles from "./SiteHeader.module.css";

const norm = (p: string) => (p.endsWith("/") ? p : `${p}/`);

export function SiteHeader() {
  const pathname = norm(usePathname() ?? "/");
  const [open, setOpen] = useState(false);

  // Close the phone menu after a navigation and on Escape.
  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <header className={styles.header}>
      <div className={styles.bar}>
        <Link href="/" className={styles.brand}>
          {site.name}
        </Link>

        <button type="button" className={styles.toggle} aria-expanded={open} aria-controls="site-nav" onClick={() => setOpen((v) => !v)}>
          {open ? "Close" : "Menu"}
        </button>

        <nav id="site-nav" className={styles.nav} data-open={open} aria-label="Main">
          <ul>
            {nav.map((item) =>
              item.ready ? (
                <li key={item.href}>
                  <Link href={item.href} aria-current={pathname === item.href ? "page" : undefined}>
                    {item.label}
                  </Link>
                </li>
              ) : (
                <li key={item.href} className={styles.soon}>
                  {item.label} <span>(not written yet)</span>
                </li>
              ),
            )}
            <li>
              <a href={site.repoUrl} rel="noopener">
                Code on GitHub
              </a>
            </li>
          </ul>
        </nav>
      </div>
    </header>
  );
}
