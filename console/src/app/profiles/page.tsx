/**
 * Profiles: how each person wants Novak to work with them (decision #78). The text lives in
 * registry/profiles/<name>.md and the gateway serves it as the tool `<name>__profile`, so an edit
 * here changes Open WebUI and every other client at once, from the next conversation.
 */
import Link from "next/link";
import { requireUser, ADMIN_GROUP } from "@/lib/authz";
import { loadPeople, personFor, registryDir } from "@/lib/people";
import { listVersions, readProfile, readVersion, MAX_CHARS } from "@/lib/profiles";
import { Editor } from "./editor";
import { restoreVersionAction, saveProfileAction } from "./actions";

type Search = Promise<{ person?: string; version?: string; saved?: string; error?: string }>;

export default async function ProfilesPage({ searchParams }: { searchParams: Search }) {
  const q = await searchParams;
  const user = await requireUser();
  const people = await loadPeople();
  const me = personFor(people, user.email);
  // Only an admin can open anyone else's. The save action checks again; this just hides the choice.
  const admin = user.groups.includes(ADMIN_GROUP);
  const visible = admin ? people : people.filter((p) => p.name === me?.name);

  if (visible.length === 0) {
    return (
      <main className="page">
        <h1>Profiles</h1>
        <p>You are signed in, but Novak does not know who you are yet. Ask whoever runs Novak to add your email address (<code>people.yaml</code>).</p>
      </main>
    );
  }

  const person = visible.find((p) => p.name === q.person)?.name ?? visible.find((p) => p.name === me?.name)?.name ?? visible[0].name;
  const root = registryDir();
  const live = await readProfile(root, person);
  const versions = await listVersions(root, person);
  const preview = q.version ? await readVersion(root, person, q.version).catch(() => null) : null;
  const shown = preview ?? live ?? "";

  return (
    <main className="page">
      <h1>Profiles</h1>
      <p className="lede">
        How you want Novak to work with you. It reads this at the start of every conversation, in Open WebUI
        and anywhere else you sign in. Keep it short and plain.
      </p>

      {visible.length > 1 && (
        <nav className="tabs" aria-label="Person">
          {visible.map((p) => (
            <Link key={p.name} href={`/profiles?person=${p.name}`} aria-current={p.name === person ? "page" : undefined}>
              {p.name}
            </Link>
          ))}
        </nav>
      )}

      {q.saved && <p className="notice ok" role="status">Saved. It takes effect in your next conversation.</p>}
      {q.error && <p className="notice danger" role="alert">{q.error}</p>}
      {live === null && !preview && (
        <p className="notice warn">{person} has no profile yet, so Novak has nothing to tell it about them. Saving one creates it.</p>
      )}
      {preview && <p className="notice warn">Showing an older version. Save to make it the current one.</p>}

      <Editor key={`${person}:${q.version ?? "live"}`} person={person} initial={shown} action={saveProfileAction} />

      <section className="stack" aria-labelledby="history">
        <h2 id="history">Earlier versions</h2>
        {versions.length === 0 ? (
          <p className="meta">None yet. The text before each change is kept here.</p>
        ) : (
          <ul className="list">
            {versions.slice(0, 10).map((v) => (
              <li key={v} className="row">
                <Link href={`/profiles?person=${person}&version=${v}`}>{v.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})Z.*/, "$1-$2-$3 $4:$5 UTC")}</Link>
                <form action={restoreVersionAction}>
                  <input type="hidden" name="person" value={person} />
                  <input type="hidden" name="version" value={v} />
                  <button type="submit" className="button quiet">Restore</button>
                </form>
              </li>
            ))}
          </ul>
        )}
        <p className="meta">Limit {MAX_CHARS} characters. Every save is recorded (who and when, never the text).</p>
      </section>
    </main>
  );
}
