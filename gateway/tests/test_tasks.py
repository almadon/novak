import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novak_gateway import tasks  # noqa: E402
from novak_gateway.approvals import Approvals  # noqa: E402
from novak_gateway.audit import Audit  # noqa: E402
from novak_gateway.service import Gateway  # noqa: E402

NOISE = {f"field_{i}": "x" * 20 for i in range(60)}


def task(id, name, due=None, priority=None, status=0, **kw):
    return {"id": id, "uid": f"u{id}", "name": name, "due_date": due, "priority": priority, "status": status, **NOISE, **kw}


class FakeTududi:
    def __init__(self, today=(), upcoming=()):
        self.lists, self.calls = {"today": list(today), "upcoming": list(upcoming)}, []

    def call(self, method, params=None):
        if method == "tools/list":
            return {"tools": []}
        self.calls.append(params)
        body = {"count": 0, "tasks": self.lists[params["arguments"]["type"]]}
        return {"content": [{"type": "text", "text": json.dumps(body)}]}


class TasksTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": [
            {"name": "tududi-1-tmeuze", "kind": "external", "url": "http://t/mcp", "enabled": True},
            {"name": "outline-1", "kind": "external", "url": "http://o/mcp", "enabled": True}]}))
        (self.dir / "people.yaml").write_text(yaml.safe_dump({
            "people": {"tmeuze": {"names": ["tmeuze"], "entries": ["tududi-1-tmeuze"]},
                       "ushy": {"names": ["ushy"], "entries": ["outline-1"]}},
            "household": {"entries": []}}))
        (self.dir / "gateway.yaml").write_text(yaml.safe_dump({"gateway": {}}))
        self.td = FakeTududi(
            today=[task(1, "Pay water bill", "2026-10-24", 2), task(2, "Old thing", "2026-10-20", 1, status=1)],
            upcoming=[task(1, "Pay water bill", "2026-10-24", 2), task(3, "Dentist", "2026-10-27", None),
                      task(4, "Someday", None), task(5, "Finished", "2026-10-25", status=2)])
        now = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc).timestamp()
        self.gw = Gateway(self.dir, Audit(str(self.dir / "a.db")), Approvals(str(self.dir / "p.db")), "http://gw",
                          {"TZ": "UTC"}, notifier=lambda *a: "x", upstream_factory=lambda url, token: self.td, clock=lambda: now)
        from novak_gateway.auth import Identity
        self.me = Identity("person", "tmeuze", "key", self.gw.dir.find_person("tmeuze"))
        self.ushy = Identity("person", "ushy", "key", self.gw.dir.find_person("ushy"))

    def call(self, who=None):
        r = self.gw.call_tool(who or self.me, "tasks__tasks_state", {})
        return r["content"][0]["text"], r.get("isError", False)

    def test_offered_only_to_someone_with_a_tududi_entry(self):
        self.assertIn("tasks__tasks_state", [t["name"] for t in self.gw.list_tools(self.me)])
        self.assertNotIn("tasks__tasks_state", [t["name"] for t in self.gw.list_tools(self.ushy)])
        text, err = self.call(self.ushy)
        self.assertTrue(err)
        self.assertIn("Unknown tool", text)

    def test_it_is_small(self):
        self.assertLess(len(json.dumps(tasks.TOOLS)), 500)

    def test_groups_by_when_with_ids_and_no_noise(self):
        text, err = self.call()
        self.assertFalse(err)
        self.assertIn("Open tasks: 4.", text)
        self.assertIn("Overdue (1):\n- #2 Old thing | due 2026-10-20 | medium | in progress", text)
        self.assertIn("Due today (1):\n- #1 Pay water bill | due 2026-10-24 | high", text)
        self.assertIn("Next 7 days (1):\n- #3 Dentist | due 2026-10-27", text)
        self.assertIn("Later or undated (1):\n- #4 Someday", text)
        self.assertNotIn("Finished", text)                    # done tasks are left out
        self.assertNotIn("field_", text)
        self.assertLess(len(text), 700)

    def test_a_task_in_both_lists_is_shown_once(self):
        self.assertEqual(self.call()[0].count("Pay water bill"), 1)

    def test_nothing_open_says_so(self):
        self.td.lists = {"today": [], "upcoming": []}
        self.assertIn("Open tasks: 0. None.", self.call()[0])

    def test_long_lists_are_cut_with_a_count(self):
        self.td.lists = {"today": [task(i, f"T{i}") for i in range(40)], "upcoming": []}
        text = self.call()[0]
        self.assertIn("(and 15 more)", text)

    def test_today_follows_the_configured_timezone(self):
        self.gw.env = {"TZ": "Pacific/Kiritimati"}            # already the 25th there
        self.assertIn("Overdue (2):", self.call()[0])

    def test_an_unreachable_tududi_is_an_error_not_a_crash(self):
        def boom(*a):
            raise OSError("down")
        self.td.call = boom
        text, err = self.call()
        self.assertTrue(err)
        self.assertIn("could not reach", text)

    def test_a_tool_allowlist_and_scope_narrow_it(self):
        self.me.tools = ("house__*",)
        self.assertNotIn("tasks__tasks_state", [t["name"] for t in self.gw.list_tools(self.me)])
        self.assertTrue(self.call()[1])
        self.me.tools = ()
        self.me.scope = ("outline-*",)
        self.assertNotIn("tasks__tasks_state", [t["name"] for t in self.gw.list_tools(self.me)])

    def test_the_audit_records_a_read(self):
        self.call()
        self.assertIn(("tasks", "tasks_state", "read", "allowed"),
                      {(r["entry"], r["tool"], r["kind"], r["decision"]) for r in self.gw.audit.recent("tmeuze")})


if __name__ == "__main__":
    unittest.main()
