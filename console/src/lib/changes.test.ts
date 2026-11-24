import assert from "node:assert/strict";
import { test } from "node:test";
import { requestForget } from "./changes.ts";

const env = { GATEWAY_URL: "http://g:8000/", GATEWAY_CHANGE_KEY: "ck" };

test("sends who, what and which memory with the change key", async () => {
  let seen: { url: string; auth: string | null; body: unknown } = { url: "", auth: null, body: null };
  const f = (async (url: string, init: RequestInit) => {
    seen = { url, auth: new Headers(init.headers).get("authorization"), body: JSON.parse(String(init.body)) };
    return new Response("{}", { status: 202 });
  }) as unknown as typeof fetch;
  assert.deepEqual(await requestForget("tmeuze", "tmeuze", "0a1b2c3d-0000", env, f), { ok: true });
  assert.equal(seen.url, "http://g:8000/admin/changes");
  assert.equal(seen.auth, "Bearer ck");
  assert.deepEqual(seen.body, { person: "tmeuze", action: "forget_memory", bank: "tmeuze", memory_id: "0a1b2c3d-0000" });
});

test("says what went wrong in words", async () => {
  const mk = (s: number) => (async () => new Response("{}", { status: s })) as unknown as typeof fetch;
  for (const [code, re] of [[401, /refused/], [403, /not yours/], [429, /waiting/], [500, /500/]] as const) {
    const r = await requestForget("a", "a", "id", env, mk(code));
    assert.equal(r.ok, false);
    assert.match((r as { message: string }).message, re);
  }
  const down = await requestForget("a", "a", "id", env, (async () => { throw new Error("x"); }) as unknown as typeof fetch);
  assert.match((down as { message: string }).message, /did not answer/);
});

test("without a key it does not call out", async () => {
  let called = false;
  const r = await requestForget("a", "a", "id", { GATEWAY_URL: "http://g" }, (async () => { called = true; return new Response(""); }) as unknown as typeof fetch);
  assert.equal(r.ok, false);
  assert.equal(called, false);
});
