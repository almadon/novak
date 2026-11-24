/**
 * Memory: what Novak remembers, read-only for now. Which banks a person may open is decided in
 * lib/memory.ts (their own and their code bank; the household one for an admin; never anyone else's).
 * Removing or correcting a memory needs the write path with phone confirmation, so it is not here yet.
 */
import Link from "next/link";
import { requireUser, ADMIN_GROUP } from "@/lib/authz";
import { loadPeople, personFor } from "@/lib/people";
import { PAGE, TYPES, banksFor, loadBanks, loadMemories } from "@/lib/memory";

export const dynamic = "force-dynamic";

type Search = Promise<{ bank?: string; q?: string; type?: string; offset?: string }>;

export default async function MemoryPage({ searchParams }: { searchParams: Search }) {
  const q = await searchParams;
  const user = await requireUser();
  const admin = user.groups.includes(ADMIN_GROUP);
  const me = personFor(await loadPeople(), user.email);
  const allowed = banksFor(me?.name, admin);

  if (allowed.length === 0) {
    return (
      <main className="page">
        <h1>Memory</h1>
        <p>Your sign-in email is not listed for anyone in <code>people.yaml</code>, so there is no memory to show.</p>
      </main>
    );
  }

  const banks = await loadBanks(allowed);
  if (banks.state !== "ok") {
    return (
      <main className="page">
        <h1>Memory</h1>
        {banks.state === "unconfigured"
          ? <p className="notice warn">The console is not set up to reach memory (HINDSIGHT_URL and HINDSIGHT_API_KEY).</p>
          : <p className="notice danger" role="alert">{banks.reason}</p>}
      </main>
    );
  }

  const open = banks.data.find((b) => b.id === q.bank) ?? banks.data[0];
  if (!open) {
    return (
      <main className="page">
        <h1>Memory</h1>
        <p>Nothing is remembered for you yet. A bank appears with its first memory.</p>
      </main>
    );
  }

  const offset = Math.max(0, Number.parseInt(q.offset ?? "0", 10) || 0);
  const type = (TYPES as readonly string[]).includes(q.type ?? "") ? q.type : undefined;
  const mem = await loadMemories(open.id, { q: q.q, type, offset });
  const link = (extra: Record<string, string | undefined>) => {
    const p = new URLSearchParams();
    const all = { bank: open.id, q: q.q, type, ...extra };
    for (const [k, v] of Object.entries(all)) if (v) p.set(k, v);
    return `/memory?${p}`;
  };

  return (
    <main className="page">
      <h1>Memory</h1>
      <p className="lede">What Novak remembers, from conversations, recordings and anything you asked it to keep. Read-only for now.</p>

      {banks.data.length > 1 && (
        <nav className="tabs" aria-label="Memory bank">
          {banks.data.map((b) => (
            <Link key={b.id} href={`/memory?bank=${b.id}`} aria-current={b.id === open.id ? "page" : undefined}>{b.label} ({b.facts})</Link>
          ))}
        </nav>
      )}

      <form method="get" action="/memory" className="row" role="search">
        <input type="hidden" name="bank" value={open.id} />
        <input type="search" name="q" defaultValue={q.q ?? ""} placeholder="Search this memory" aria-label="Search this memory" maxLength={200} />
        <select name="type" defaultValue={type ?? ""} aria-label="Kind">
          <option value="">All kinds</option>
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button type="submit" className="button quiet">Search</button>
      </form>

      {mem.state === "down" && <p className="notice danger" role="alert">{mem.reason}</p>}
      {mem.state === "ok" && (
        <section className="stack" aria-label="Memories">
          <p className="meta">{mem.data.total === 0 ? "Nothing matches." : `${offset + 1} to ${Math.min(offset + PAGE, mem.data.total)} of ${mem.data.total}`}</p>
          <ul className="list">
            {mem.data.items.map((m) => (
              <li key={m.id} className="memory">
                <p>{m.text}</p>
                <p className="meta">
                  {m.type}{m.date && ` · ${m.date.slice(0, 10)}`}{m.tags.length > 0 && ` · ${m.tags.join(", ")}`}
                  {m.state && m.state !== "valid" && ` · ${m.state}`}
                </p>
                {m.context && <p className="meta">{m.context}</p>}
              </li>
            ))}
          </ul>
          <p className="row">
            {offset > 0 ? <Link href={link({ offset: String(Math.max(0, offset - PAGE)) })}>Newer</Link> : <span />}
            {offset + PAGE < mem.data.total && <Link href={link({ offset: String(offset + PAGE) })}>Older</Link>}
          </p>
        </section>
      )}
      <p className="meta">To correct or remove a memory today, ask Novak in Open WebUI. Editing here comes with confirmation on your phone.</p>
    </main>
  );
}
