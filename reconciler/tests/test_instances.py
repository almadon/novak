import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "reconciler" / "instances.py"


class Home:
    def __init__(self, test, env_extra=""):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "registry").mkdir()
        self.reg = self.dir / "registry" / "mcp-servers.yaml"
        self.reg.write_text((REPO / "registry" / "mcp-servers.yaml").read_text())
        (self.dir / ".env").write_text("HOST_NAME=spire\n" + env_extra)

    def run(self, *args, stdin=""):
        env = {**os.environ, "NOVAK_HOME": str(self.dir)}
        return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin,
                              capture_output=True, text=True, env=env)

    def entries(self):
        return {e["name"]: e for e in yaml.safe_load(self.reg.read_text())["servers"]}


class AddTests(unittest.TestCase):
    def test_hindsight_bank_added_with_comments_intact(self):
        h = Home(self)
        before = h.reg.read_text()
        r = h.run("add", "--kind", "hindsight", "--name", "ushy", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        after = h.reg.read_text()
        self.assertTrue(after.startswith(before))          # nothing above was rewritten
        e = h.entries()["hindsight-ushy"]
        self.assertTrue(e["url"].endswith("/mcp/ushy/"))
        self.assertEqual((e["auth"], e["clients"]), ("HINDSIGHT_API_KEY", ["open-webui"]))
        self.assertEqual(e["risk"]["level"], "elevated")
        self.assertIn("accepted_on", e["risk"])
        self.assertEqual(r.stdout.strip(), "SECRETS:")       # same tenant key, no new secret
        self.assertEqual(len(list(h.dir.glob("registry/*.bak-*"))), 1)

    def test_voice_safe_bank_goes_to_home_assistant(self):
        h = Home(self)
        h.run("add", "--kind", "hindsight", "--name", "kitchen", "--set", "voice_safe=y", "--yes")
        e = h.entries()["hindsight-kitchen"]
        self.assertEqual(e["clients"], ["home-assistant"])
        self.assertEqual(len(e["risk"]["why"]), 1)           # no "personal memories" warning

    def test_new_bank_copies_the_host_of_an_existing_one(self):
        h = Home(self)
        text = h.reg.read_text().replace("http://EDIT-ME:8888/mcp/tmeuze/", "http://100.64.0.9:13403/mcp/tmeuze/")
        h.reg.write_text(text)
        h.run("add", "--kind", "hindsight", "--name", "ushy", "--yes")
        self.assertEqual(h.entries()["hindsight-ushy"]["url"], "http://100.64.0.9:13403/mcp/ushy/")

    def test_duplicate_is_refused_and_registry_untouched(self):
        h = Home(self)
        r = h.run("add", "--kind", "hindsight", "--name", "tmeuze", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already exists", r.stderr)
        self.assertEqual(h.reg.read_text(), (REPO / "registry" / "mcp-servers.yaml").read_text())

    def test_outline_and_tududi_get_their_own_secret_names(self):
        h = Home(self)
        r = h.run("add", "--kind", "outline", "--name", "work", "--set", "url=https://w.example/mcp", "--yes")
        self.assertEqual(r.stdout.strip(), "SECRETS: OUTLINE_WORK_API_KEY")
        self.assertEqual(h.entries()["outline-work"]["auth"], "OUTLINE_WORK_API_KEY")
        r = h.run("add", "--kind", "tududi", "--name", "ushy-home", "--set", "url=https://t.example/api/mcp", "--yes")
        self.assertEqual(r.stdout.strip(), "SECRETS: TUDUDI_USHY_HOME_API_TOKEN")

    def test_vikunja_instance_maps_env_and_takes_a_free_port(self):
        h = Home(self)
        r = h.run("add", "--kind", "vikunja", "--name", "partner",
                  "--set", "url=https://tasks.example", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        e = h.entries()["vikunja-partner"]
        used = {x["port"] for n, x in h.entries().items() if n != "vikunja-partner" and "port" in x}
        self.assertNotIn(e["port"], used)
        self.assertEqual(e["env"], ["VIKUNJA_URL=VIKUNJA_PARTNER_URL",
                                    "VIKUNJA_API_TOKEN=VIKUNJA_PARTNER_API_TOKEN"])
        self.assertIn("VIKUNJA_PARTNER_URL=https://tasks.example", (h.dir / ".env").read_text())
        self.assertEqual(r.stdout.strip(), "SECRETS: VIKUNJA_PARTNER_API_TOKEN")

    def test_vikunja_container_receives_the_mapped_values(self):
        h = Home(self, "VIKUNJA_PARTNER_URL=https://tasks.example\nVIKUNJA_PARTNER_API_TOKEN=tok\n")
        h.run("add", "--kind", "vikunja", "--name", "partner", "--set", "url=https://tasks.example", "--yes")
        env = {**os.environ, "NOVAK_HOME": str(h.dir)}
        out = subprocess.run([sys.executable, str(REPO / "reconciler" / "reconcile.py"), "--dry-run"],
                             capture_output=True, text=True, env=env).stdout
        svc = yaml.safe_load(out[out.index("name:"):])["services"]["vikunja-partner-mcp"]
        self.assertEqual(svc["environment"]["VIKUNJA_URL"], "${VIKUNJA_PARTNER_URL}")
        self.assertEqual(svc["environment"]["VIKUNJA_API_TOKEN"], "${VIKUNJA_PARTNER_API_TOKEN}")

    def test_invalid_entry_is_rolled_back(self):
        h = Home(self)
        before = h.reg.read_text()
        r = h.run("add", "--kind", "mcp", "--name", "bad", "--set", "url=not-a-url",
                  "--set", "needs_token=n", "--yes")
        self.assertEqual(r.returncode, 1)
        self.assertIn("put back", r.stderr)
        self.assertEqual(h.reg.read_text(), before)

    def test_elevated_needs_acceptance_without_yes(self):
        h = Home(self)
        r = h.run("add", "--kind", "hindsight", "--name", "ushy", "--set", "voice_safe=n",
                  "--set", "base=http://hindsight:8888", "--set", "accept=n")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not accepted", r.stderr)
        self.assertNotIn("hindsight-ushy", h.entries())

    def test_super_productivity_is_external_and_warns(self):
        h = Home(self)
        r = h.run("add", "--kind", "super-productivity", "--name", "home",
                  "--set", "url=http://desk.local:3876/mcp", "--set", "needs_token=n", "--yes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("no official MCP", r.stderr)
        self.assertEqual(h.entries()["super-productivity-home"]["kind"], "external")

    def test_dry_run_writes_nothing(self):
        h = Home(self)
        before = h.reg.read_text()
        r = h.run("add", "--kind", "hindsight", "--name", "ushy", "--yes", "--dry-run")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(h.reg.read_text(), before)
        self.assertEqual(list(h.dir.glob("registry/*.bak-*")), [])

    def test_secret_vars_include_instance_credentials_only(self):
        h = Home(self)
        h.run("add", "--kind", "vikunja", "--name", "partner", "--set", "url=https://t.example", "--yes")
        h.run("add", "--kind", "outline", "--name", "work", "--set", "url=https://w.example/mcp", "--yes")
        names = h.run("secret-vars").stdout.split()
        for n in ("VIKUNJA_PARTNER_API_TOKEN", "OUTLINE_WORK_API_KEY", "HINDSIGHT_API_KEY"):
            self.assertIn(n, names)
        self.assertNotIn("VIKUNJA_PARTNER_URL", names)


if __name__ == "__main__":
    unittest.main()
