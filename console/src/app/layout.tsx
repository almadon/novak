import "@/styles/globals.css";
import Link from "next/link";
import { cookies } from "next/headers";
import { COOKIE, decode } from "@/lib/appearance";
import { BUILTIN, loadThemes, themeCss } from "@/lib/themes";
import { registryDir } from "@/lib/people";
import { Mark } from "@/components/mark";
import { Nav } from "@/components/nav";

export const metadata = {
  title: "Novak Console",
  description: "What Novak did today, what it remembers, and what is waiting for your yes",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const look = decode((await cookies()).get(COOKIE)?.value);
  const { themes } = await loadThemes(registryDir());
  const theme = themes.find((t) => t.id === look.theme) ?? BUILTIN[0];

  return (
    <html
      lang="en"
      data-theme={look.mode === "system" ? undefined : look.mode}
      data-text={look.text}
      data-contrast={look.contrast}
      data-motion={look.motion}
    >
      <head>
        {/* Built only from validated hex colours: see lib/themes.ts. */}
        <style dangerouslySetInnerHTML={{ __html: themeCss(theme) }} />
      </head>
      <body>
        <a className="skip" href="#content">Skip to content</a>
        <header className="masthead">
          <div className="masthead-inner">
            <Link href="/" className="brand"><Mark /><span>Novak</span></Link>
            <Nav />
          </div>
        </header>
        <div id="content" tabIndex={-1}>{children}</div>
      </body>
    </html>
  );
}
