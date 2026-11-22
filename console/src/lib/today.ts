/**
 * The Today page's data: one read-only call to the gateway (GET /admin/today). The key it holds opens
 * that path and nothing else, so the console can show what happened without being able to do anything.
 *
 * The response is parsed field by field into known shapes rather than passed through, so a surprise from
 * the other side (or something it should never have sent) cannot reach a page.
 *
 * No imports from "@/…" so the node test runner can load this file directly.
 */

export interface PendingApproval { id: number; person: string; entry: string; tool: string; createdAt: number }
export interface DecidedApproval extends PendingApproval { status: string; decidedAt: number | null }
export interface ActivityRow {
  ts: number; person: string; via: string; entry: string; tool: string; kind: string;
  decision: string; outcome: string; ms: number;
}
export interface Today {
  now: number;
  gateway: { people: number; entries: number; problems: string[] };
  pending: PendingApproval[];
  decided: DecidedApproval[];
  activity: { since: number; calls: number; errors: number; byDecision: Record<string, number>; byPerson: Record<string, number>; recent: ActivityRow[] };
}

export type TodayResult =
  | { state: "ok"; data: Today }
  | { state: "unconfigured" }
  | { state: "down"; reason: string };

const str = (v: unknown, max = 200): string => (typeof v === "string" ? v.slice(0, max) : "");
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});
const counts = (v: unknown): Record<string, number> =>
  Object.fromEntries(Object.entries(obj(v)).slice(0, 50).map(([k, n]) => [k.slice(0, 80), num(n)]));

const pending = (v: unknown): PendingApproval => {
  const o = obj(v);
  return { id: num(o.id), person: str(o.person), entry: str(o.entry), tool: str(o.tool), createdAt: num(o.created_at) };
};

export function parseToday(raw: unknown): Today {
  const o = obj(raw);
  const g = obj(o.gateway), a = obj(o.approvals), act = obj(o.activity);
  return {
    now: num(o.now),
    gateway: { people: num(g.people), entries: num(g.entries), problems: arr(g.problems).map((p) => str(p, 300)).slice(0, 20) },
    pending: arr(a.pending).slice(0, 50).map(pending),
    decided: arr(a.recent).slice(0, 20).map((v) => {
      const o2 = obj(v);
      return { ...pending(v), status: str(o2.status, 20), decidedAt: o2.decided_at == null ? null : num(o2.decided_at) };
    }),
    activity: {
      since: num(act.since), calls: num(act.calls), errors: num(act.errors),
      byDecision: counts(act.by_decision), byPerson: counts(act.by_person),
      recent: arr(act.recent).slice(0, 50).map((v) => {
        const r = obj(v);
        return { ts: num(r.ts), person: str(r.person), via: str(r.via), entry: str(r.entry), tool: str(r.tool),
                 kind: str(r.kind), decision: str(r.decision, 20), outcome: str(r.outcome), ms: num(r.ms) };
      }),
    },
  };
}

export async function fetchToday(
  person?: string,
  env: Record<string, string | undefined> = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<TodayResult> {
  const base = env.GATEWAY_URL?.replace(/\/$/, "");
  const key = env.GATEWAY_ADMIN_KEY;
  if (!base || !key) return { state: "unconfigured" };
  try {
    const url = `${base}/admin/today${person ? `?person=${encodeURIComponent(person)}` : ""}`;
    const res = await fetchImpl(url, {
      headers: { Authorization: `Bearer ${key}` },
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (res.status === 401) return { state: "down", reason: "The gateway refused the console's status key." };
    if (!res.ok) return { state: "down", reason: `The gateway answered ${res.status}.` };
    return { state: "ok", data: parseToday(await res.json()) };
  } catch {
    return { state: "down", reason: "The gateway did not answer." };
  }
}

/** "3 min ago", from two unix-second timestamps. */
export function ago(now: number, then: number): string {
  const s = Math.max(0, now - then);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

/** What an audit row means in a sentence, for a person rather than a log reader. */
export function describe(r: ActivityRow): string {
  const tool = (r.tool || "a tool").replace(/_/g, " ");
  const where = r.entry && r.entry !== "tools/list" ? ` (${r.entry})` : "";
  switch (r.decision) {
    case "denied": return `${r.person} was refused ${tool}`;
    case "held": return `${r.person} asked to ${tool}${where}; waiting for a yes`;
    case "approved": return `${r.person} was allowed ${tool}${where} after confirming`;
    case "expired": return `${r.person} asked to ${tool}${where}; nobody confirmed`;
    case "error": return `${tool}${where} failed for ${r.person}`;
    default: return r.outcome.startsWith("error") ? `${tool}${where} failed for ${r.person}` : `${r.person} used ${tool}${where}`;
  }
}
