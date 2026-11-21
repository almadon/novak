"use server";
/**
 * Saving a profile. Two ways to be allowed, and no third:
 *  - it is your own profile (your Pocket ID email is listed for that person in people.yaml);
 *  - you are an admin, checked again with Pocket ID right now (requireAdmin), acting on anyone's.
 * Someone else's profile steers what their assistant does, so it is admin-only, and the audit line
 * records which of the two it was.
 */
import { redirect } from "next/navigation";
import { AuthzError, requireAdmin, requireUser } from "@/lib/authz";
import { loadPeople, personFor, registryDir } from "@/lib/people";
import { ProfileError, readVersion, saveProfile, type Actor } from "@/lib/profiles";

async function allowed(person: string): Promise<Actor> {
  const user = await requireUser();
  const people = await loadPeople();
  if (!people.some((p) => p.name === person)) throw new ProfileError("There is no such person.");
  if (personFor(people, user.email)?.name === person) return { sub: user.sub, as: "self" };
  const admin = await requireAdmin(); // revalidates with Pocket ID
  return { sub: admin.sub, as: "admin" };
}

function back(person: string, note: string): never {
  redirect(`/profiles?person=${encodeURIComponent(person)}&${note}`);
}

export async function saveProfileAction(form: FormData): Promise<void> {
  const person = String(form.get("person") ?? "");
  try {
    const actor = await allowed(person);
    await saveProfile(registryDir(), person, form.get("text"), actor, "save");
  } catch (err) {
    if (err instanceof ProfileError) back(person, `error=${encodeURIComponent(err.message)}`);
    if (err instanceof AuthzError) back(person, `error=${encodeURIComponent("You can only change your own profile.")}`);
    throw err;
  }
  back(person, "saved=1");
}

export async function restoreVersionAction(form: FormData): Promise<void> {
  const person = String(form.get("person") ?? "");
  const version = String(form.get("version") ?? "");
  try {
    const actor = await allowed(person);
    const text = await readVersion(registryDir(), person, version);
    if (text === null) throw new ProfileError("That version no longer exists.");
    await saveProfile(registryDir(), person, text, actor, "restore");
  } catch (err) {
    if (err instanceof ProfileError) back(person, `error=${encodeURIComponent(err.message)}`);
    if (err instanceof AuthzError) back(person, `error=${encodeURIComponent("You can only change your own profile.")}`);
    throw err;
  }
  back(person, "saved=1");
}
