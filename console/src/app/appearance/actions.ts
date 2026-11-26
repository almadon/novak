"use server";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/authz";
import { COOKIE, DEFAULTS, clean, encode } from "@/lib/appearance";

export async function saveAppearanceAction(form: FormData): Promise<void> {
  await requireUser();
  const next = form.get("reset") ? DEFAULTS : clean(Object.fromEntries(form) as Record<string, unknown>);
  (await cookies()).set(COOKIE, encode(next), { path: "/", maxAge: 60 * 60 * 24 * 365, sameSite: "lax", httpOnly: true });
  redirect("/appearance?saved=1");
}
