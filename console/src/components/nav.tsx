"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

// A new page gets into the header by adding one line here.
const PAGES = [
  { href: "/", label: "Today" },
  { href: "/approvals", label: "Approvals" },
  { href: "/memory", label: "Memory" },
  { href: "/profiles", label: "Profiles" },
  { href: "/appearance", label: "Appearance" },
];

/** The same links on every page, with the current one marked. Admin pages are linked from Today, for admins only. */
export function Nav() {
  const path = usePathname();
  return (
    <nav className="nav" aria-label="Pages">
      {PAGES.map((p) => (
        <Link key={p.href} href={p.href} aria-current={path === p.href ? "page" : undefined}>{p.label}</Link>
      ))}
    </nav>
  );
}
