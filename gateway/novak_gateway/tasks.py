"""A compact tasks snapshot: one small tool in place of reading Tududi's raw task JSON (decision #74).

Tududi's `list_tasks` returns about seventy fields per task (around 2,000 characters each), far more than
an 8,192-token model can afford. `tasks_state` asks for today's and upcoming tasks and boils each down to a
line: id, name, due date, priority. Like `house_state` it is a ledger: call it once at the start of a chat,
refer back to it, and call it again only after a change or when asked. Add and complete go through the
ordinary Tududi tools, which take the ids shown here.

Built on the person's own Tududi entry (their credential, their tasks), offered only to someone who has one.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SEP = "__"
ALIAS = "tasks"
MAX_SHOWN = 25
STATUS = {0: "", "not_started": "", 1: "in progress", "in_progress": "in progress", 4: "waiting", "waiting": "waiting"}
FINISHED = {2, 3, 5, "done", "archived", "cancelled"}
PRIORITY = {2: "high", "high": "high", 1: "medium", "medium": "medium"}

TOOLS = [
    {"name": "tasks_state",
     "description": "The person's open tasks: overdue, due today, coming up, with ids. Call once at the start "
                    "of a chat; call again after changes or when asked.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def _text(msg: str, error=False) -> dict:
    return {"content": [{"type": "text", "text": msg}], "isError": error}


class Tasks:
    def __init__(self, gateway):
        self.gw = gateway

    def entry_for(self, identity):
        """The person's own Tududi entry, or None (then the tool is not offered)."""
        if identity.kind == "household" or not identity.person:
            return None
        return next((e for e in self.gw.dir.entries_for(identity.person) if e.name.startswith("tududi")), None)

    def tools(self) -> list[dict]:
        return [{**t, "name": f"{ALIAS}{SEP}{t['name']}"} for t in TOOLS]

    def today(self) -> datetime:
        tz = self.gw.env.get("TZ") or self.gw.env.get("INGEST_TZ") or "UTC"
        try:
            return datetime.fromtimestamp(self.gw.clock(), ZoneInfo(tz))
        except Exception:
            return datetime.fromtimestamp(self.gw.clock(), timezone.utc)

    def _list(self, entry, kind: str) -> list[dict]:
        res = self.gw._upstream(entry).call("tools/call", {"name": "list_tasks", "arguments": {"type": kind, "limit": 100}})
        text = " ".join(c.get("text", "") for c in res.get("content", []))
        if res.get("isError"):
            raise RuntimeError(text[:200] or "Tududi refused the lookup")
        try:
            tasks = json.loads(text)["tasks"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError(f"unexpected answer from Tududi ({exc})") from None
        return [t for t in tasks if isinstance(t, dict)]

    @staticmethod
    def _line(t: dict) -> str:
        bits = [f"#{t.get('id')} {str(t.get('name') or '').strip()[:80]}"]
        due = str(t.get("due_date") or "")[:10]
        if due:
            bits.append(f"due {due}" + (f" {str(t['due_time'])[:5]}" if t.get("due_time") else ""))
        for label in (PRIORITY.get(t.get("priority")), STATUS.get(t.get("status"))):
            if label:
                bits.append(label)
        return " | ".join(bits)

    def tasks_state(self, entry, args: dict) -> dict:
        seen, rows = set(), []
        for kind in ("today", "upcoming"):
            for t in self._list(entry, kind):
                if t.get("id") in seen or t.get("status") in FINISHED:
                    continue
                seen.add(t.get("id"))
                rows.append(t)
        now = self.today()
        today, soon = now.date().isoformat(), (now + timedelta(days=7)).date().isoformat()

        def due(t):
            return re.match(r"\d{4}-\d{2}-\d{2}", str(t.get("due_date") or "")) and str(t["due_date"])[:10]
        groups = {"Overdue": [], "Due today": [], "Next 7 days": [], "Later or undated": []}
        for t in sorted(rows, key=lambda t: (due(t) or "9999", str(t.get("due_time") or ""))):
            d = due(t)
            groups["Overdue" if d and d < today else "Due today" if d == today else "Next 7 days" if d and d <= soon
                   else "Later or undated"].append(t)
        lines = [now.strftime("Now: %a %d %b %Y %H:%M."), f"Open tasks: {len(rows)}." + ("" if rows else " None.")]
        shown = 0
        for name, ts in groups.items():
            if not ts:
                continue
            lines.append(f"{name} ({len(ts)}):")
            for t in ts[:max(0, MAX_SHOWN - shown)]:
                lines.append("- " + self._line(t))
                shown += 1
        if len(rows) > shown:
            lines.append(f"(and {len(rows) - shown} more)")
        return _text("\n".join(lines))

    def call(self, entry, tool: str, args: dict) -> tuple[dict, str]:
        if tool == "tasks_state":
            return self.tasks_state(entry, args), "read"
        return _text(f"Unknown tool 'tasks{SEP}{tool}'.", True), "read"
