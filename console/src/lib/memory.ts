/**
 * Memory: a read-only window onto a person's Hindsight banks. The console holds Hindsight's one tenant
 * key (decision: banks share a tenant), so which bank a person may open is decided HERE and nowhere
 * else, from who they are:
 *
 *   - their own bank (`<name>`) and their code bank (`code-<name>`), only for themselves;
 *   - the household bank, only for an admin;
 *   - never another person's, not even an admin's. Reading someone's memories is not an admin power.
 *
 * Everything coming back is parsed field by field, and the bank id is checked against a fixed shape
 * before it goes anywhere near a URL. No imports from "@/…" so the node test runner can load this.
 */

export const PAGE = 20;
export const TYPES = ["world", "experience", "observation"] as const;
export type FactType = (typeof TYPES)[number];

const BANK_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/;

export interface Bank { id: string; label: string; facts: number; lastWrite: string | null }
export interface Memory { id: string; text: string; context: string; type: string; date: string; tags: string[]; state: string }
export interface MemoryPage { total: number; items: Memory[]; offset: number }

export type Loaded<T> = { state: "ok"; data: T } | { state: "unconfigured" } | { state: "down"; reason: string };

/** The banks this person may ask for. A bank that does not exist in Hindsight is dropped later. */
export function banksFor(person: string | undefined, admin: boolean): { id: string; label: string }[] {
  const out: { id: string; label: string }[] = [];
  if (person && BANK_RE.test(person)) {
    out.push({ id: person, label: "Personal" });
    out.push({ id: `code-${person}`, label: "Code projects" });
  }
  if (admin) out.push({ id: "household", label: "Household" });
  return out;
}

const str = (v: unknown, max = 4000): string => (typeof v === "string" ? v.slice(0, max) : "");
const num = (v: unknown): number => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const obj = (v: unknown): Record<string, unknown> => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {});

export function parseBanks(raw: unknown): Map<string, Bank> {
  const out = new Map<string, Bank>();
  for (const b of arr(obj(raw).banks)) {
    const o = obj(b), id = str(o.bank_id, 64);
    if (BANK_RE.test(id)) out.set(id, { id, label: id, facts: num(o.fact_count), lastWrite: str(o.last_write_at, 40) || null });
  }
  return out;
}

export function parseMemories(raw: unknown): MemoryPage {
  const o = obj(raw);
  return {
    total: num(o.total), offset: num(o.offset),
    items: arr(o.items).slice(0, 100).map((v) => {
      const m = obj(v);
      return {
        id: str(m.id, 80), text: str(m.text), context: str(m.context, 500), type: str(m.fact_type, 30),
        date: str(m.date, 40), tags: arr(m.tags).filter((t): t is string => typeof t === "string").slice(0, 12).map((t) => t.slice(0, 40)),
        state: str(m.state, 20),
      };
    }),
  };
}

type Env = Record<string, string | undefined>;

async function call(path: string, env: Env, fetchImpl: typeof fetch): Promise<Loaded<unknown>> {
  const base = env.HINDSIGHT_URL?.replace(/\/$/, "");
  if (!base || !env.HINDSIGHT_API_KEY) return { state: "unconfigured" };
  try {
    const res = await fetchImpl(`${base}/v1/default${path}`, {
      headers: { Authorization: `Bearer ${env.HINDSIGHT_API_KEY}` },
      cache: "no-store",
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return { state: "down", reason: `Memory answered ${res.status}.` };
    return { state: "ok", data: await res.json() };
  } catch {
    return { state: "down", reason: "Memory did not answer." };
  }
}

export async function loadBanks(allowed: { id: string; label: string }[], env: Env = process.env, fetchImpl: typeof fetch = fetch): Promise<Loaded<Bank[]>> {
  const r = await call("/banks", env, fetchImpl);
  if (r.state !== "ok") return r;
  const have = parseBanks(r.data);
  return { state: "ok", data: allowed.flatMap((a) => { const b = have.get(a.id); return b ? [{ ...b, label: a.label }] : []; }) };
}

/** `bank` must come from banksFor(); this re-checks the shape anyway, because it ends up in a URL. */
export async function loadMemories(
  bank: string,
  opts: { q?: string; type?: string; offset?: number },
  env: Env = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<Loaded<MemoryPage>> {
  if (!BANK_RE.test(bank)) return { state: "down", reason: "Not a memory bank." };
  const p = new URLSearchParams({ limit: String(PAGE), offset: String(Math.max(0, Math.floor(opts.offset ?? 0))) });
  const q = opts.q?.trim().slice(0, 200);
  if (q) p.set("q", q);
  if (opts.type && (TYPES as readonly string[]).includes(opts.type)) p.set("type", opts.type);
  const r = await call(`/banks/${bank}/memories/list?${p}`, env, fetchImpl);
  return r.state === "ok" ? { state: "ok", data: parseMemories(r.data) } : r;
}
