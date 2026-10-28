import Link from "next/link";
import styles from "./Chips.module.css";

/** A row of small links that work like the filter chips at the top of a messenger's list. */
export function Chips({ label, items }: { label: string; items: { href: string; text: string; current: boolean }[] }) {
  return (
    <nav className={styles.chips} aria-label={label}>
      {items.map((item) => (
        <Link key={item.href} href={item.href} aria-current={item.current ? "true" : undefined}>
          {item.text}
        </Link>
      ))}
    </nav>
  );
}
