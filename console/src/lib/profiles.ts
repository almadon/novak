/**
 * A person's standing instructions: registry/profiles/<name>.md, which the gateway serves to that
 * person as the tool `<name>__profile` (decision #78).
 *
 * The one place the console writes outside its own state, so it is deliberately narrow:
 *  - the file name comes from people.yaml, never from a request, and is checked again here;
 *  - text is capped (the local models have an 8,192-token window) and must be plain text;
 *  - a save is an atomic rename, so the gateway never reads half a file;
 *  - the previous text is kept in profiles/.history/<name>/ and every write adds a line to
 *    profiles/.audit.jsonl (who, when, how long, a hash: never the text itself).
 *
 * No imports from "@/…" so the node test runner can load this file directly.
 */
import { createHash } from "node:crypto";
import { appendFile, mkdir, readFile, readdir, rename, writeFile } from "node:fs/promises";
import path from "node:path";

export const MAX_CHARS = 4000;
export const KEEP_VERSIONS = 30;
const NAME_RE = /^[a-z0-9][a-z0-9_-]*$/;
const VERSION_RE = /^\d{8}T\d{6}Z(-\d+)?$/;

export class ProfileError extends Error {}

export interface Actor {
  /** Pocket ID subject of whoever is saving. */
  sub: string;
  /** What they did it as: their own profile, or an admin acting on someone else's. */
  as: "self" | "admin";
}

function dir(root: string): string {
  return path.join(root, "profiles");
}

export function assertName(name: string): string {
  if (!NAME_RE.test(name)) throw new ProfileError("That is not a valid person name.");
  return name;
}

export function validateText(text: unknown): string {
  if (typeof text !== "string") throw new ProfileError("The profile must be text.");
  const t = text.replace(/\r\n/g, "\n").replace(/\s+$/, "") + "\n";
  if (t.trim() === "") throw new ProfileError("The profile is empty. Delete the file on the host to switch it off.");
  if (t.includes("\0")) throw new ProfileError("The profile has a character that is not allowed.");
  if (t.length - 1 > MAX_CHARS) throw new ProfileError(`The profile is ${t.length - 1} characters; the limit is ${MAX_CHARS}.`);
  return t;
}

async function readOrNull(file: string): Promise<string | null> {
  try {
    return await readFile(file, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw err;
  }
}

export async function readProfile(root: string, name: string): Promise<string | null> {
  return readOrNull(path.join(dir(root), `${assertName(name)}.md`));
}

export async function listVersions(root: string, name: string): Promise<string[]> {
  try {
    const files = await readdir(path.join(dir(root), ".history", assertName(name)));
    return files.filter((f) => f.endsWith(".md") && VERSION_RE.test(f.slice(0, -3))).map((f) => f.slice(0, -3)).sort().reverse();
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

export async function readVersion(root: string, name: string, version: string): Promise<string | null> {
  if (!VERSION_RE.test(version)) throw new ProfileError("That is not a saved version.");
  return readOrNull(path.join(dir(root), ".history", assertName(name), `${version}.md`));
}

function stamp(now: Date): string {
  return now.toISOString().replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
}

export async function saveProfile(
  root: string, name: string, text: unknown, actor: Actor, action: "save" | "restore" = "save", now = new Date(),
): Promise<void> {
  assertName(name);
  const clean = validateText(text);
  await mkdir(path.join(dir(root), ".history", name), { recursive: true });

  const current = await readProfile(root, name);
  if (current !== null && current === clean) return; // nothing changed: no new version, no noise
  if (current !== null) {
    let version = stamp(now);
    const taken = new Set(await listVersions(root, name));
    for (let n = 1; taken.has(version); n++) version = `${stamp(now)}-${n}`;
    await writeFile(path.join(dir(root), ".history", name, `${version}.md`), current, { flag: "wx" });
  }

  const target = path.join(dir(root), `${name}.md`);
  const tmp = path.join(dir(root), `.${name}.md.tmp`);
  await writeFile(tmp, clean, { mode: 0o644 });
  await rename(tmp, target); // atomic: the gateway reads the old file or the new one, never half

  const line = JSON.stringify({
    ts: now.toISOString(), sub: actor.sub, as: actor.as, person: name, action,
    chars: clean.length - 1, sha256: createHash("sha256").update(clean).digest("hex"),
  });
  await appendFile(path.join(dir(root), ".audit.jsonl"), line + "\n");
}
