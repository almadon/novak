import sys
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novak_gateway import profile  # noqa: E402
from novak_gateway.approvals import Approvals  # noqa: E402
from novak_gateway.audit import Audit  # noqa: E402
from novak_gateway.auth import Identity  # noqa: E402
from novak_gateway.service import Gateway  # noqa: E402


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": []}))
        (self.dir / "people.yaml").write_text(yaml.safe_dump({
            "people": {"tmeuze": {"names": ["tmeuze"], "entries": []}, "ushy": {"names": ["ushy"], "entries": []}},
            "household": {"entries": []}}))
        (self.dir / "gateway.yaml").write_text(yaml.safe_dump({"gateway": {}}))
        (self.dir / "profiles").mkdir()
        (self.dir / "profiles" / "tmeuze.md").write_text("Be brief. Three priorities at most.\n")
        self.gw = Gateway(self.dir, Audit(str(self.dir / "a.db")), Approvals(str(self.dir / "p.db")), "http://gw", {},
                          notifier=lambda *a: "x")
        self.me = Identity("person", "tmeuze", "key", self.gw.dir.find_person("tmeuze"))
        self.ushy = Identity("person", "ushy", "key", self.gw.dir.find_person("ushy"))

    def names(self, who):
        return [t["name"] for t in self.gw.list_tools(who)]

    def test_the_tool_is_named_after_the_person_and_only_they_have_it(self):
        self.assertIn("tmeuze__profile", self.names(self.me))
        self.assertNotIn("tmeuze__profile", self.names(self.ushy))      # no file for ushy, and not hers anyway
        r = self.gw.call_tool(self.ushy, "tmeuze__profile", {})
        self.assertTrue(r["isError"])
        self.assertNotIn("Be brief", r["content"][0]["text"])

    def test_it_returns_the_file_and_is_read_fresh_each_time(self):
        self.assertEqual(self.gw.call_tool(self.me, "tmeuze__profile", {})["content"][0]["text"],
                         "Be brief. Three priorities at most.")
        (self.dir / "profiles" / "tmeuze.md").write_text("Changed.\n")
        self.assertEqual(self.gw.call_tool(self.me, "tmeuze__profile", {})["content"][0]["text"], "Changed.")

    def test_a_person_gets_their_own_when_both_have_one_and_not_the_others(self):
        (self.dir / "profiles" / "ushy.md").write_text("Ushy's rules.\n")
        self.assertEqual(self.gw.call_tool(self.ushy, "ushy__profile", {})["content"][0]["text"], "Ushy's rules.")
        self.assertTrue(self.gw.call_tool(self.ushy, "tmeuze__profile", {})["isError"])

    def test_the_household_and_an_unnamed_caller_never_get_one(self):
        hh = Identity("household", "household", "key")
        self.assertEqual([n for n in self.names(hh) if n.endswith("__profile")], [])
        self.assertTrue(self.gw.call_tool(hh, "household__profile", {})["isError"])

    def test_a_long_profile_is_cut_with_a_note(self):
        (self.dir / "profiles" / "tmeuze.md").write_text("x" * (profile.MAX_CHARS + 500))
        text = self.gw.call_tool(self.me, "tmeuze__profile", {})["content"][0]["text"]
        self.assertLess(len(text), profile.MAX_CHARS + 120)
        self.assertIn("Cut short", text)

    def test_it_is_small_and_the_description_tells_the_model_when_to_call_it(self):
        t = next(t for t in self.gw.list_tools(self.me) if t["name"] == "tmeuze__profile")
        self.assertLess(len(str(t)), 400)
        self.assertIn("start of every conversation", t["description"])

    def test_allowlist_and_scope_narrow_it(self):
        self.me.tools = ("house__*",)
        self.assertNotIn("tmeuze__profile", self.names(self.me))
        self.assertTrue(self.gw.call_tool(self.me, "tmeuze__profile", {})["isError"])
        self.me.tools = ("*__profile",)
        self.assertIn("tmeuze__profile", self.names(self.me))
        self.me.tools, self.me.scope = (), ("house",)
        self.assertNotIn("tmeuze__profile", self.names(self.me))

    def test_the_audit_records_a_read_by_name_without_the_text(self):
        self.gw.call_tool(self.me, "tmeuze__profile", {})
        rows = self.gw.audit.recent("tmeuze")
        self.assertIn(("tmeuze", "profile", "read", "allowed"), {(r["entry"], r["tool"], r["kind"], r["decision"]) for r in rows})
        self.assertNotIn("Be brief", str(rows))

    def test_a_username_that_could_escape_the_folder_gets_nothing(self):
        bad = Identity("person", "../etc/passwd", "key", self.gw.dir.find_person("tmeuze"))
        self.assertIsNone(self.gw.profile.alias(bad))


if __name__ == "__main__":
    unittest.main()
