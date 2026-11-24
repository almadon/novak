import assert from "node:assert/strict";
import { test } from "node:test";
import { banksFor, loadBanks, loadMemories, parseBanks, parseMemories } from "./memory.ts";

test("a person opens their own banks, never another person's", () => {
  assert.deepEqual(banksFor("tmeuze", false).map((b) => b.id), ["tmeuze", "code-tmeuze"]);
  assert.deepEqual(banksFor("tmeuze", true).map((b) => b.id), ["tmeuze", "code-tmeuze", "household"]);
  assert.ok(!banksFor("tmeuze", true).some((b) => b.id.includes("ushy")));
});

test("an admin who is not a person still gets only the household", () => {
  assert.deepEqual(banksFor(undefined, true).map((b) => b.id), ["household"]);
  assert.deepEqual(banksFor(undefined, false), []);
});

test("a person name that could escape the path yields no bank", () => {
  assert.deepEqual(banksFor("../admin", false), []);
  assert.deepEqual(banksFor("a/b", false), []);
});

test("banks Hindsight lacks are dropped, and unsafe ids are ignored", async () => {
  const body = { banks: [{ bank_id: "tmeuze", fact_count: 4 }, { bank_id: "ushy", fact_count: 9 }, { bank_id: "../x" }] };
  const f = (async () => new Response(JSON.stringify(body))) as unknown as typeof fetch;
  const r = await loadBanks(banksFor("tmeuze", false), { HINDSIGHT_URL: "http://h", HINDSIGHT_API_KEY: "k" }, f);
  assert.equal(r.state, "ok");
  if (r.state === "ok") assert.deepEqual(r.data.map((b) => [b.id, b.label, b.facts]), [["tmeuze", "Personal", 4]]);
  assert.equal(parseBanks(body).has("../x"), false);
});

test("memories are parsed field by field", () => {
  const p = parseMemories({ total: 1, offset: 0, items: [{ id: "a", text: "t", fact_type: "world", tags: ["x", 5], embedding: [1, 2], date: "d" }] });
  assert.equal(p.items[0].text, "t");
  assert.deepEqual(p.items[0].tags, ["x"]);
  assert.ok(!JSON.stringify(p).includes("embedding"));
  assert.equal(parseMemories(null).items.length, 0);
});

test("the request carries the key, paging and only whitelisted filters", async () => {
  let url = "", auth: string | null = null;
  const f = (async (u: string, init: RequestInit) => { url = u; auth = new Headers(init.headers).get("authorization"); return new Response("{}"); }) as unknown as typeof fetch;
  await loadMemories("tmeuze", { q: " coffee ", type: "bogus", offset: 40 }, { HINDSIGHT_URL: "http://h:8888/", HINDSIGHT_API_KEY: "k" }, f);
  assert.equal(url, "http://h:8888/v1/default/banks/tmeuze/memories/list?limit=20&offset=40&q=coffee");
  assert.equal(auth, "Bearer k");
});

test("a bad bank is refused before any request is made", async () => {
  let called = false;
  const f = (async () => { called = true; return new Response("{}"); }) as unknown as typeof fetch;
  const r = await loadMemories("../x", {}, { HINDSIGHT_URL: "http://h", HINDSIGHT_API_KEY: "k" }, f);
  assert.equal(r.state, "down");
  assert.equal(called, false);
});

test("unconfigured without a key", async () => {
  assert.equal((await loadMemories("tmeuze", {}, { HINDSIGHT_URL: "http://h" })).state, "unconfigured");
});
