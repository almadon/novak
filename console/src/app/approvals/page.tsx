/**
 * Approvals: changes waiting for a yes, and how recent ones were answered. The answer is always given on
 * the phone (or the Home Assistant buttons); this page only shows it, so a stolen console session cannot
 * approve anything. Everyone sees their own; an admin sees everyone's.
 */
import { requireUser, ADMIN_GROUP } from "@/lib/authz";
import { loadPeople, personFor } from "@/lib/people";
import { ago, fetchToday, label } from "@/lib/today";

export const dynamic = "force-dynamic";

export default async function Approvals() {
  const user = await requireUser();
  const admin = user.groups.includes(ADMIN_GROUP);
  const me = personFor(await loadPeople(), user.email);
  if (!admin && !me) {
    return <main className="page"><h1>Approvals</h1><p>You are signed in, but Novak does not know who you are yet. Ask whoever runs Novak to add your email address (<code>people.yaml</code>).</p></main>;
  }
  const r = await fetchToday(admin ? undefined : me?.name);

  return (
    <main className="page">
      <h1>Approvals</h1>
      <p className="lede">Changes that wait for a yes. You answer on your phone; this page only shows what is waiting and how it went.</p>
      {r.state === "unconfigured" && <p className="notice warn">The console has no status key for the gateway yet (<code>novak gateway admin-key</code>).</p>}
      {r.state === "down" && <p className="notice danger" role="alert">{r.reason}</p>}
      {r.state === "ok" && (
        <>
          <section className="stack" aria-labelledby="waiting">
            <h2 id="waiting">Waiting</h2>
            {r.data.pending.length === 0 ? <p className="empty">Nothing is waiting. New requests appear here and on your phone.</p> : (
              <ul className="list">
                {r.data.pending.map((p) => (
                  <li key={p.id} className="row">
                    <span>{p.person}: <strong>{label(p.tool)}</strong> ({p.entry})</span>
                    <span className="meta">asked {ago(r.data.now, p.createdAt)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="meta">A request that is not answered in a few minutes expires and nothing changes.</p>
          </section>
          <section className="stack" aria-labelledby="decided">
            <h2 id="decided">Recently answered</h2>
            {r.data.decided.length === 0 ? <p className="empty">Nothing yet. Answered requests are listed here.</p> : (
              <ul className="list">
                {r.data.decided.map((d) => (
                  <li key={d.id} className="row">
                    <span>{d.person}: {label(d.tool)} was <span className={`pill ${d.status}`}>{d.status}</span></span>
                    <span className="meta">{ago(r.data.now, d.decidedAt ?? d.createdAt)}</span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </main>
  );
}
