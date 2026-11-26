/** Appearance: colour scheme and the display options, remembered on this device only. */
import { cookies } from "next/headers";
import { requireUser } from "@/lib/authz";
import { registryDir } from "@/lib/people";
import { loadThemes, type Palette } from "@/lib/themes";
import { COOKIE, OPTIONS, decode } from "@/lib/appearance";
import { saveAppearanceAction } from "./actions";

export const dynamic = "force-dynamic";

/** A tiny picture of a page in one palette. Decorative: the theme's name carries the meaning. */
function Swatch({ p }: { p: Palette }) {
  return (
    <svg viewBox="0 0 60 40" aria-hidden="true" focusable="false">
      <rect width="60" height="40" fill={p.bg} />
      <rect x="6" y="7" width="48" height="26" rx="5" fill={p.surface} stroke={p.border} />
      <rect x="12" y="13" width="26" height="3" rx="1.5" fill={p.text} />
      <rect x="12" y="19" width="34" height="2.5" rx="1.25" fill={p["text-muted"]} />
      <rect x="12" y="25" width="16" height="5" rx="2.5" fill={p.accent} />
    </svg>
  );
}

export default async function AppearancePage({ searchParams }: { searchParams: Promise<{ saved?: string }> }) {
  const q = await searchParams;
  await requireUser();
  const now = decode((await cookies()).get(COOKIE)?.value);
  const { themes, refused } = await loadThemes(registryDir());
  const chosen = themes.some((t) => t.id === now.theme) ? now.theme : "clay";

  return (
    <main className="page">
      <h1>Appearance</h1>
      <p className="lede">How Novak looks on this device. Other devices and other people keep their own choice.</p>
      {q.saved && <p className="notice ok" role="status">Saved.</p>}

      <form action={saveAppearanceAction} className="stack">
        <fieldset>
          <legend>Colour scheme</legend>
          <div className="themes">
            {themes.map((t) => (
              <label key={t.id} className="theme">
                <input type="radio" name="theme" value={t.id} defaultChecked={t.id === chosen} />
                <span className="swatches"><Swatch p={t.light} /><Swatch p={t.dark} /></span>
                <span className="label">{t.label}</span>
                <span className="meta">{t.about}</span>
              </label>
            ))}
          </div>
        </fieldset>

        {(Object.keys(OPTIONS) as (keyof typeof OPTIONS)[]).map((key) => (
          <fieldset key={key}>
            <legend>{OPTIONS[key].label}</legend>
            <div className="choices">
              {Object.entries(OPTIONS[key].choices).map(([value, label]) => (
                <label key={value} className="choice">
                  <input type="radio" name={key} value={value} defaultChecked={now[key] === value} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
          </fieldset>
        ))}

        <div className="row">
          <button type="submit" name="reset" value="1" className="button ghost">Back to the defaults</button>
          <button type="submit" className="button">Save</button>
        </div>
      </form>

      {refused.length > 0 && (
        <section className="stack" aria-labelledby="refused">
          <h2 id="refused">Schemes that could not be used</h2>
          <ul className="list">
            {refused.map((r) => <li key={r.file}><code>themes/{r.file}</code>: {r.error}</li>)}
          </ul>
        </section>
      )}
    </main>
  );
}
