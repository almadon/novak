/**
 * Today: what needs a person's attention and what Novak did, at a glance. Read-only. Everything here
 * comes from the gateway's status endpoint (lib/today.ts); an admin sees the household, anyone else
 * sees only their own rows (the person filter is applied by the gateway, not by this page).
 */
import Link from "next/link";
import { requireUser, ADMIN_GROUP } from "@/lib/authz";
import { loadPeople, personFor } from "@/lib/people";
import { ago, describe, fetchToday } from "@/lib/today";

export const dynamic = "force-dynamic";

export default async function Today() {
  const user = await requireUser();
  const admin = user.groups.includes(ADMIN_GROUP);
  const me = personFor(await loadPeople(), user.email);

  if (!admin && !me) {
    return (
      <main className="page">
        <h1>Today</h1>
        <p>You are signed in, but Novak does not know who you are yet. Ask whoever runs Novak to add your email address (<code>people.yaml</code>).</p>
      </main>
    );
  }

  const result = await fetchToday(admin ? undefined : me?.name);

  return (
    <main className="page">
      <h1>Today</h1>
      <p className="lede">
        {admin ? "The household" : `Your activity, ${me?.name}`}: what is waiting on someone, and what Novak has done since midnight.
      </p>

      {result.state === "unconfigured" && (
        <p className="notice warn">
          The console has no status key for the gateway yet. Run <code>novak gateway admin-key</code>, store it with{" "}
          <code>novak secret set CONSOLE_GATEWAY_KEY</code>, then <code>novak up</code>.
        </p>
      )}
      {result.state === "down" && <p className="notice danger" role="alert">{result.reason}</p>}

      {result.state === "ok" && (() => {
        const t = result.data;
        const a = t.activity;
        return (
          <>
            {admin && t.gateway.problems.length > 0 && (
              <section className="stack" aria-labelledby="problems">
                <h2 id="problems">Needs fixing</h2>
                <ul className="list">
                  {t.gateway.problems.map((p) => <li key={p} className="notice warn">{p}</li>)}
                </ul>
              </section>
            )}

            <section className="stack" aria-labelledby="waiting">
              <h2 id="waiting">Waiting for a yes</h2>
              {t.pending.length === 0 ? (
                <p className="meta">Nothing is waiting. Removals ask for confirmation on the phone of the person who asked.</p>
              ) : (
                <ul className="list">
                  {t.pending.map((p) => (
                    <li key={p.id} className="row">
                      <span>{p.person} asked to <strong>{p.tool.replace(/_/g, " ")}</strong> ({p.entry})</span>
                      <span className="meta">{ago(t.now, p.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="meta">Approving happens on the phone, never here.</p>
            </section>

            <section className="stack" aria-labelledby="numbers">
              <h2 id="numbers">Since midnight</h2>
              <dl className="stats">
                <div><dt>Calls</dt><dd>{a.calls}</dd></div>
                <div><dt>Refused</dt><dd className={a.byDecision.denied ? "danger" : undefined}>{a.byDecision.denied ?? 0}</dd></div>
                <div><dt>Errors</dt><dd className={a.errors ? "danger" : undefined}>{a.errors}</dd></div>
                {admin && <div><dt>People</dt><dd>{t.gateway.people}</dd></div>}
                {admin && <div><dt>Entries</dt><dd>{t.gateway.entries}</dd></div>}
              </dl>
              {admin && Object.keys(a.byPerson).length > 0 && (
                <p className="meta">By person: {Object.entries(a.byPerson).map(([n, c]) => `${n} ${c}`).join(", ")}</p>
              )}
            </section>

            <section className="stack" aria-labelledby="recent">
              <h2 id="recent">Latest</h2>
              {a.recent.length === 0 ? (
                <p className="meta">Nothing yet.</p>
              ) : (
                <ul className="list">
                  {a.recent.slice(0, 15).map((r, i) => (
                    <li key={`${r.ts}-${i}`} className="row">
                      <span className={r.decision === "denied" || r.decision === "error" || r.outcome.startsWith("error") ? "danger" : undefined}>{describe(r)}</span>
                      <span className="meta">{ago(t.now, r.ts)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="meta">Shows who did what, never what was said or stored.</p>
            </section>

            {t.decided.length > 0 && (
              <section className="stack" aria-labelledby="decided">
                <h2 id="decided">Recent decisions</h2>
                <ul className="list">
                  {t.decided.slice(0, 5).map((d) => (
                    <li key={d.id} className="row">
                      <span>{d.person}: {d.tool.replace(/_/g, " ")} was <strong>{d.status}</strong></span>
                      <span className="meta">{ago(t.now, d.decidedAt ?? d.createdAt)}</span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </>
        );
      })()}

      <p className="meta">
        <Link href="/approvals">Approvals</Link> · <Link href="/memory">Memory</Link> · <Link href="/profiles">Profiles</Link>{admin && <> · <Link href="/admin">Admin: tool catalog</Link></>}
      </p>
    </main>
  );
}
