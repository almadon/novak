/**
 * Who is who. The gateway names a person by a short username (`tmeuze`); the console knows the
 * signed-in person by their Pocket ID email. registry/people.yaml is where the two meet, so this
 * reads it and nothing else decides who a person is.
 *
 * No imports from "@/…" so the node test runner can load this file directly.
 */
import { readFile } from "node:fs/promises";
import path from "node:path";
import { parse } from "yaml";

export interface Person {
  name: string;
  emails: string[];
  names: string[];
}

export function registryDir(): string {
  return process.env.REGISTRY_DIR ?? path.join(process.cwd(), "registry");
}

const strings = (v: unknown): string[] =>
  Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];

export function parsePeople(text: string): Person[] {
  const doc = parse(text) as { people?: Record<string, Record<string, unknown>> } | null;
  return Object.entries(doc?.people ?? {}).map(([name, p]) => ({
    name,
    emails: strings(p?.emails).map((e) => e.toLowerCase()),
    names: strings(p?.names).map((n) => n.toLowerCase()),
  }));
}

export async function loadPeople(root = registryDir()): Promise<Person[]> {
  try {
    return parsePeople(await readFile(path.join(root, "people.yaml"), "utf8"));
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return [];
    throw err;
  }
}

/** The person a signed-in user is, matched by email only: a display name is not an identity. */
export function personFor(people: Person[], email?: string): Person | undefined {
  const e = email?.trim().toLowerCase();
  return e ? people.find((p) => p.emails.includes(e)) : undefined;
}
