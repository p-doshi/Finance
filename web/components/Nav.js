import Link from "next/link";
import { useRouter } from "next/router";

// Tabs beyond My Portfolio / Explore are placeholders for pages not built
// yet (Underdogs risk screen, Recommendations) -- listed so the shape of
// the eventual app is visible now, not added silently later.
const TABS = [
  { href: "/", label: "My Portfolio" },
  { href: "/explore", label: "Explore" },
  { href: "/underdogs", label: "Underdogs", soon: true },
  { href: "/recommendations", label: "Recommendations", soon: true },
];

export default function Nav() {
  const router = useRouter();
  return (
    <nav
      style={{
        display: "flex",
        gap: 4,
        padding: "12px 16px 0",
        maxWidth: 820,
        margin: "0 auto",
        borderBottom: "1px solid var(--border)",
      }}
    >
      {TABS.map((t) => {
        const active = router.pathname === t.href;
        const content = (
          <span
            style={{
              display: "inline-block",
              padding: "8px 12px",
              fontSize: 13,
              fontWeight: active ? 650 : 500,
              color: t.soon ? "var(--muted)" : active ? "var(--text-primary)" : "var(--text-secondary)",
              borderBottom: active ? "2px solid var(--text-primary)" : "2px solid transparent",
              cursor: t.soon ? "default" : "pointer",
            }}
          >
            {t.label}
            {t.soon && <span style={{ fontSize: 10, marginLeft: 4 }}>(soon)</span>}
          </span>
        );
        return t.soon ? (
          <span key={t.href}>{content}</span>
        ) : (
          <Link key={t.href} href={t.href} style={{ textDecoration: "none" }}>
            {content}
          </Link>
        );
      })}
    </nav>
  );
}
