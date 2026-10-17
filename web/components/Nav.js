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
    <nav className="nav">
      <div className="nav-inner">
        {TABS.map((t) => {
          const active = router.pathname === t.href;
          const className = `tab${active ? " active" : ""}${t.soon ? " soon" : ""}`;
          const content = (
            <>
              {t.label}
              {t.soon && <span className="tab-flag">soon</span>}
            </>
          );
          return t.soon ? (
            <span key={t.href} className={className}>
              {content}
            </span>
          ) : (
            <Link key={t.href} href={t.href} className={className}>
              {content}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
