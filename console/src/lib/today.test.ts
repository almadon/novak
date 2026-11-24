import assert from "node:assert/strict";
import { test } from "node:test";
import { ago, describe, fetchToday, parseToday } from "./today.ts";

const sample = {
  now: 1000,
  gateway: { people: 2, entries: 9, problems: ["x: entry 'y' is not enabled"] },
  approvals: {
    pending: [{ id: 3, person: "tmeuze", entry: "hs", tool: "delete_document", status: "pending", created_at: 900, decided_at: null, token: "LEAK" }],
    recent: [{ id: 2, person: "ushy", entry: "hs", tool: "delete_note", status: "denied", created_at: 100, decided_at: 120 }],
  },
  activity: {
    since: 0, calls: 3, errors: 1, by_decision: { allowed: 2, denied: 1 }, by_person: { tmeuze: 3 },
    recent: [{ ts: 990, person: "tmeuze", via: "key", entry: "hs", tool: "recall", kind: "read", decision: "allowed", outcome: "", ms: 12, arg_names: "[\"query\"]" }],
  },
};

test("parses known fields and drops everything else", () => {
  const t = parseToday(sample);
  assert.equal(t.pending[0].tool, "delete_document");
  assert.equal(t.decided[0].status, "denied");
  assert.equal(t.activity.byDecision.allowed, 2);
  assert.ok(!JSON.stringify(t).includes("LEAK"));
  assert.ok(!JSON.stringify(t).includes("arg_names"));
});

test("survives garbage without throwing", () => {
  for (const bad of [null, 5, "x", [], { gateway: 3, approvals: [], activity: { recent: "no" } }]) {
    const t = parseToday(bad);
    assert.equal(t.pending.length, 0);
    assert.equal(t.activity.calls, 0);
  }
});

test("unconfigured without a key, and never calls out", async () => {
  let called = false;
  const r = await fetchToday(undefined, { GATEWAY_URL: "http://g" }, (async () => { called = true; return new Response("{}"); }) as typeof fetch);
  assert.equal(r.state, "unconfigured");
  assert.equal(called, false);
});

test("sends the key as a bearer token and the person as a query", async () => {
  let seen: { url: string; auth: string | null } = { url: "", auth: null };
  const f = (async (url: string, init: RequestInit) => {
    seen = { url, auth: new Headers(init.headers).get("authorization") };
    return new Response(JSON.stringify(sample));
  }) as unknown as typeof fetch;
  const r = await fetchToday("tmeuze", { GATEWAY_URL: "http://g:8000/", GATEWAY_ADMIN_KEY: "k" }, f);
  assert.equal(r.state, "ok");
  assert.equal(seen.url, "http://g:8000/admin/today?person=tmeuze");
  assert.equal(seen.auth, "Bearer k");
});

test("reports a refusal, an error status and a dead gateway differently", async () => {
  const env = { GATEWAY_URL: "http://g", GATEWAY_ADMIN_KEY: "k" };
  const mk = (s: number) => (async () => new Response("{}", { status: s })) as unknown as typeof fetch;
  const a = await fetchToday(undefined, env, mk(401));
  const b = await fetchToday(undefined, env, mk(500));
  const c = await fetchToday(undefined, env, (async () => { throw new Error("boom"); }) as unknown as typeof fetch);
  for (const r of [a, b, c]) assert.equal(r.state, "down");
  assert.match((a as { reason: string }).reason, /refused/);
  assert.match((b as { reason: string }).reason, /500/);
});

test("ago and describe read like sentences", () => {
  assert.equal(ago(100, 90), "just now");
  assert.equal(ago(1000, 700), "5 min ago");
  assert.equal(ago(100000, 90000), "2 h ago");
  const row = parseToday(sample).activity.recent[0];
  assert.equal(describe(row), "tmeuze used recall (hs)");
  assert.equal(describe({ ...row, decision: "denied" }), "tmeuze was refused recall");
  assert.equal(describe({ ...row, tool: "tools/list", entry: "tududi-1-tmeuze", decision: "error" }), "tududi-1-tmeuze could not list its tools for tmeuze");
});
