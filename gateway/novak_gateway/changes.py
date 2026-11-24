"""Changes the console asks for. The console never decides anything and never proxies a tool call: it
says "this person asked for this change" and the gateway holds it for that person's yes on their phone
(the same approval as a removal asked for through Open WebUI), then does it as that person, with that
person's own credential, and records it.

The asker is trusted only as far as its key goes (gateway.yaml admin.change_key_sha256): a stolen key
can make a phone buzz, nothing more. Every action is on a short fixed list, its parameters are checked
here, and the entry it touches must be one of that person's own.
"""
import re
import threading

from .auth import Identity

MEMORY_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
MAX_PENDING_PER_PERSON = 3


class ChangeError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status, self.message = status, message


class Changes:
    def __init__(self, gw, run_async=True):
        self.gw, self.run_async = gw, run_async

    # What each action is: which tool it runs, on which entry, and how to say it to a person.
    def _forget_memory(self, person, params):
        bank, memory_id = str(params.get("bank", "")), str(params.get("memory_id", ""))
        entry_name = {person.name: f"hindsight-{person.name}", f"code-{person.name}": f"code-memory-{person.name}"}.get(bank)
        if not entry_name or entry_name not in person.entries:
            raise ChangeError(403, "not one of this person's memory banks")
        if not MEMORY_ID_RE.match(memory_id):
            raise ChangeError(400, "not a memory id")
        return (entry_name, "invalidate_memory", {"memory_id": memory_id, "reason": "forgotten from the console"},
                "Forget a memory", f"Forget one memory in {bank}? It can be restored later.")

    ACTIONS = {"forget_memory": "_forget_memory"}

    def request(self, person_name: str, action: str, params: dict) -> None:
        person = self.gw.dir.people.get(person_name)
        if not person:
            raise ChangeError(404, "no such person")
        method = self.ACTIONS.get(action)
        if not method:
            raise ChangeError(400, "unknown action")
        entry_name, tool, args, title, summary = getattr(self, method)(person, params or {})
        entry = self.gw.dir.entries.get(entry_name)
        if not entry:
            raise ChangeError(409, f"{entry_name} is not an enabled entry")
        pending = [p for p in self.gw.approvals.listing(person.name)["pending"]]
        if len(pending) >= MAX_PENDING_PER_PERSON:
            raise ChangeError(429, "too many requests are waiting for a yes")
        job = lambda: self._run(person, entry, tool, args, title, summary)
        if self.run_async:
            threading.Thread(target=job, daemon=True).start()
        else:
            job()

    def _run(self, person, entry, tool, args, title, summary):
        gw = self.gw
        ident = Identity("person", person.name, "console", person)
        t0 = gw.clock()
        verdict = gw._confirm(ident, entry, tool, args, title=title, summary=summary)
        if verdict != "approved":
            gw.audit.record(ident, entry.name, tool, "destructive", verdict, ms=(gw.clock() - t0) * 1000, args=args)
            return
        try:
            result = gw._upstream(entry).call("tools/call", {"name": tool, "arguments": args})
            outcome = "error" if result.get("isError") else "ok"
        except Exception as exc:
            outcome = f"error: {exc}"
        gw.audit.record(ident, entry.name, tool, "destructive", "approved", outcome, (gw.clock() - t0) * 1000, args)
