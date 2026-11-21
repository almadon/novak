import assert from "node:assert/strict";
import { mkdtemp, readFile, readdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";
import { MAX_CHARS, ProfileError, listVersions, readProfile, readVersion, saveProfile, validateText } from "./profiles.ts";
import { parsePeople, personFor } from "./people.ts";

const actor = { sub: "sub-1", as: "self" } as const;
const root = () => mkdtemp(path.join(tmpdir(), "konzol-"));

test("a save is written, and the first save has no history", async () => {
  const r = await root();
  await saveProfile(r, "tmeuze", "Be brief.", actor);
  assert.equal(await readProfile(r, "tmeuze"), "Be brief.\n");
  assert.deepEqual(await listVersions(r, "tmeuze"), []);
});

test("a second save keeps the previous text as a version, and restoring one is another save", async () => {
  const r = await root();
  await saveProfile(r, "tmeuze", "One", actor, "save", new Date("2026-11-21T10:00:00Z"));
  await saveProfile(r, "tmeuze", "Two", actor, "save", new Date("2026-11-21T10:01:00Z"));
  const versions = await listVersions(r, "tmeuze");
  assert.equal(versions.length, 1);
  assert.equal(await readVersion(r, "tmeuze", versions[0]), "One\n");
  await saveProfile(r, "tmeuze", (await readVersion(r, "tmeuze", versions[0]))!, actor, "restore", new Date("2026-11-21T10:02:00Z"));
  assert.equal(await readProfile(r, "tmeuze"), "One\n");
  assert.equal((await listVersions(r, "tmeuze")).length, 2);
});

test("saving the same text again changes nothing and adds no version or audit line", async () => {
  const r = await root();
  await saveProfile(r, "tmeuze", "Same", actor);
  await saveProfile(r, "tmeuze", "Same\n", actor);
  assert.deepEqual(await listVersions(r, "tmeuze"), []);
  const audit = (await readFile(path.join(r, "profiles", ".audit.jsonl"), "utf8")).trim().split("\n");
  assert.equal(audit.length, 1);
});

test("the audit line says who and how much, never what", async () => {
  const r = await root();
  await saveProfile(r, "tmeuze", "A secret plan", { sub: "sub-9", as: "admin" });
  const raw = await readFile(path.join(r, "profiles", ".audit.jsonl"), "utf8");
  const entry = JSON.parse(raw);
  assert.equal(entry.sub, "sub-9");
  assert.equal(entry.as, "admin");
  assert.equal(entry.chars, 13);
  assert.ok(!raw.includes("secret plan"));
});

test("names that could leave the folder are refused before anything is touched", async () => {
  const r = await root();
  for (const bad of ["../etc/passwd", "a/b", "", "Tmeuze", ".hidden", "a b"]) {
    await assert.rejects(saveProfile(r, bad, "x", actor), ProfileError);
  }
  assert.deepEqual(await readdir(r), []);
});

test("text is checked: type, empty, NUL, and the length limit", () => {
  assert.throws(() => validateText(42), ProfileError);
  assert.throws(() => validateText("   \n"), ProfileError);
  assert.throws(() => validateText("a\0b"), ProfileError);
  assert.throws(() => validateText("x".repeat(MAX_CHARS + 1)), ProfileError);
  assert.equal(validateText("x".repeat(MAX_CHARS)).length, MAX_CHARS + 1);
  assert.equal(validateText("a\r\nb  \n\n"), "a\nb\n");
});

test("a version name must look like a version", async () => {
  const r = await root();
  await assert.rejects(readVersion(r, "tmeuze", "../../people"), ProfileError);
});

test("people: matched by email only, case-insensitively", () => {
  const people = parsePeople("people:\n  tmeuze:\n    names: [tmeuze]\n    emails: [Tyler@Example.org]\n  ushy:\n    emails: [u@example.org]\n");
  assert.equal(personFor(people, "tyler@example.org")?.name, "tmeuze");
  assert.equal(personFor(people, "nobody@example.org"), undefined);
  assert.equal(personFor(people, undefined), undefined);
  assert.equal(personFor(people, "tmeuze"), undefined, "a username is not an email");
});
