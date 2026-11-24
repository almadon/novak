/**
 * Asking the gateway for a change. The console never makes the change and never decides it: it tells the
 * gateway "this person asked for this", the gateway holds it for that person's yes on their phone, and
 * only then does it, as that person. The key held here can do nothing else (decision #79).
 *
 * No imports from "@/…" so the node test runner can load this file directly.
 */

export type ChangeResult = { ok: true } | { ok: false; message: string };

const messages: Record<number, string> = {
  401: "The gateway refused the console's change key.",
  403: "That is not yours to change.",
  404: "The gateway does not know that person.",
  429: "Too many requests are already waiting for your yes. Answer those on your phone first.",
};

export async function requestForget(
  person: string,
  bank: string,
  memoryId: string,
  env: Record<string, string | undefined> = process.env,
  fetchImpl: typeof fetch = fetch,
): Promise<ChangeResult> {
  const base = env.GATEWAY_URL?.replace(/\/$/, "");
  const key = env.GATEWAY_CHANGE_KEY;
  if (!base || !key) return { ok: false, message: "The console has no change key for the gateway yet (novak gateway change-key)." };
  try {
    const res = await fetchImpl(`${base}/admin/changes`, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ person, action: "forget_memory", bank, memory_id: memoryId }),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (res.status === 202) return { ok: true };
    return { ok: false, message: messages[res.status] ?? `The gateway answered ${res.status}.` };
  } catch {
    return { ok: false, message: "The gateway did not answer." };
  }
}
