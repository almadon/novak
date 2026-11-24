"use server";
/**
 * Forgetting a memory. The console only asks: the gateway holds the request for the person's yes on their
 * phone and does it as them afterwards. Whose memory may be asked about is decided here from who is signed
 * in (own and code banks; the household bank is read-only), and the gateway checks it again.
 */
import { redirect } from "next/navigation";
import { requireUser } from "@/lib/authz";
import { requestForget } from "@/lib/changes";
import { banksFor } from "@/lib/memory";
import { loadPeople, personFor } from "@/lib/people";

export async function forgetMemoryAction(form: FormData): Promise<void> {
  const bank = String(form.get("bank") ?? "");
  const memoryId = String(form.get("memory_id") ?? "");
  const back = (note: string): never => redirect(`/memory?bank=${encodeURIComponent(bank)}&${note}`);

  const user = await requireUser();
  const me = personFor(await loadPeople(), user.email);
  // admin=false on purpose: nobody, an admin included, asks to change a bank that is not theirs.
  if (!me || !banksFor(me.name, false).some((b) => b.id === bank)) return back("error=" + encodeURIComponent("That is not your memory."));

  const r = await requestForget(me.name, bank, memoryId);
  return back(r.ok ? "asked=1" : "error=" + encodeURIComponent(r.message));
}
