import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
PEOPLE_PY = REPO / "reconciler" / "people.py"
sys.path.insert(0, str(REPO / "gateway"))

REGISTRY = {"servers": [
    {"name": "outline-everything", "kind": "external", "url": "https://w.example/mcp", "auth": "OUTLINE_EVERYTHING_API_KEY", "enabled": True},
    {"name": "tududi-tui", "kind": "external", "url": "https://t.example/api/mcp", "auth": "TUDUDI_TUI_API_TOKEN", "enabled": True},
    {"name": "tududi-ushy", "kind": "external", "url": "https://t.example/api/mcp", "auth": "TUDUDI_USHY_API_TOKEN", "enabled": True},
    {"name": "hindsight-household", "kind": "external", "url": "http://hs:8888/mcp/household/", "auth": "HINDSIGHT_API_KEY", "enabled": True},
    {"name": "brave-search", "image": "node", "port": 8299, "enabled": True,
     "risk": {"level": "standard"}},
]}


class Home:
    def __init__(self, test):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        reg = self.dir / "registry"
        reg.mkdir()
        (reg / "mcp-servers.yaml").write_text(yaml.safe_dump(REGISTRY))
        (reg / "people.yaml").write_text((REPO / "registry" / "people.yaml").read_text())
        (reg / "gateway.yaml").write_text((REPO / "registry" / "gateway.yaml").read_text())
        self.people, self.gateway = reg / "people.yaml", reg / "gateway.yaml"

    def run(self, *args, env=None):
        return subprocess.run([sys.executable, str(PEOPLE_PY), *args], capture_output=True, text=True,
                              env={**os.environ, "NOVAK_HOME": str(self.dir), **(env or {})})

    def load(self):
        return yaml.safe_load(self.people.read_text())


class PersonTests(unittest.TestCase):
    def test_add_person_keeps_the_header_and_stores_only_a_hash(self):
        h = Home(self)
        before = h.people.read_text()
        r = h.run("add", "tmeuze", "--yes", "--emails", "t@example.com", "--entries", "outline-everything,tududi-tui",
                  "--ticker", "Novak tmeuze")
        self.assertEqual(r.returncode, 0, r.stderr)
        text = h.people.read_text()
        self.assertTrue(text.startswith(before.rstrip("\n").rsplit("\npeople:", 1)[0]))      # comments intact
        key = [l.strip() for l in r.stderr.splitlines() if l.strip() and len(l.strip()) > 30 and " " not in l.strip()][0]
        self.assertNotIn(key, text)                                                          # never stored
        p = h.load()["people"]["tmeuze"]
        self.assertEqual(p["key_sha256"], hashlib.sha256(key.encode()).hexdigest())
        self.assertEqual((p["names"], p["emails"], p["entries"]), (["tmeuze"], ["t@example.com"], ["outline-everything", "tududi-tui"]))
        self.assertEqual(p["notify"], {"kind": "ticker", "category": "Novak tmeuze"})

    def test_two_people_can_be_added_and_listed(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes", "--entries", "tududi-tui")
        h.run("add", "ushy", "--yes", "--entries", "tududi-ushy")
        self.assertEqual(sorted(h.load()["people"]), ["tmeuze", "ushy"])
        out = h.run("list").stderr
        self.assertIn("tmeuze", out); self.assertIn("ushy", out)

    def test_an_entry_belongs_to_one_person(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes", "--entries", "tududi-tui")
        r = h.run("add", "ushy", "--yes", "--entries", "tududi-tui")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("already owned", r.stderr + r.stdout)
        self.assertNotIn("ushy", (h.load().get("people") or {}))
        h.run("add", "ushy", "--yes")
        r = h.run("attach", "ushy", "tududi-tui")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("one credential stands for one person", r.stderr + r.stdout)

    def test_unknown_entry_is_refused(self):
        h = Home(self)
        self.assertNotEqual(h.run("add", "x", "--yes", "--entries", "nope").returncode, 0)

    def test_attach_detach_and_key_rotation(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes")
        h.run("attach", "tmeuze", "outline-everything", "tududi-tui")
        self.assertEqual(h.load()["people"]["tmeuze"]["entries"], ["outline-everything", "tududi-tui"])
        h.run("detach", "tmeuze", "tududi-tui")
        self.assertEqual(h.load()["people"]["tmeuze"]["entries"], ["outline-everything"])
        old = h.load()["people"]["tmeuze"]["key_sha256"]
        h.run("key", "tmeuze")
        self.assertNotEqual(h.load()["people"]["tmeuze"]["key_sha256"], old)

    def test_household_share_refuses_a_personal_entry(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes", "--entries", "tududi-tui")
        self.assertEqual(h.run("share", "brave-search", "hindsight-household").returncode, 0)
        self.assertEqual(h.load()["household"]["entries"], ["brave-search", "hindsight-household"])
        self.assertNotEqual(h.run("share", "tududi-tui").returncode, 0)
        h.run("unshare", "brave-search")
        self.assertEqual(h.load()["household"]["entries"], ["hindsight-household"])

    def test_trusted_client_and_household_key_edit_the_right_files(self):
        h = Home(self)
        before = h.gateway.read_text()
        r = h.run("client", "open-webui")
        self.assertEqual(r.returncode, 0, r.stderr)
        g = yaml.safe_load(h.gateway.read_text())["gateway"]
        self.assertEqual(g["clients"][0]["name"], "open-webui")
        self.assertIn("# Gateway behaviour", h.gateway.read_text())                          # comments intact
        self.assertEqual(g["confirm"], ["destructive"])
        h.run("client", "open-webui")                                                        # rotate, not duplicate
        self.assertEqual(len(yaml.safe_load(h.gateway.read_text())["gateway"]["clients"]), 1)
        h.run("household-key")
        self.assertTrue(h.load()["household"]["key_sha256"])

    def test_the_gateway_reads_what_the_cli_wrote(self):
        from novak_gateway import directory
        from novak_gateway.auth import authenticate
        h = Home(self)
        r = h.run("add", "ushy", "--yes", "--entries", "tududi-ushy")
        key = [l.strip() for l in r.stderr.splitlines() if l.strip() and len(l.strip()) > 30 and " " not in l.strip()][0]
        d = directory.load(h.dir / "registry")
        ident = authenticate(d, {"Authorization": f"Bearer {key}"}, None)
        self.assertEqual((ident.kind, ident.name), ("person", "ushy"))
        self.assertEqual([e.name for e in d.entries_for(ident.person)], ["tududi-ushy"])
        self.assertEqual(directory.validate(d), [])


class GatewayEnvTests(unittest.TestCase):
    def test_only_the_credentials_the_directory_names_reach_the_file(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes", "--entries", "outline-everything")
        h.run("share", "hindsight-household")
        env = {"OUTLINE_EVERYTHING_API_KEY": "outline-secret", "HINDSIGHT_API_KEY": "hs-secret",
               "TUDUDI_TUI_API_TOKEN": "not-listed-for-anyone", "BRAVE_API_KEY": "unrelated",
               "GATEWAY_HA_TOKEN": "set-in-keychain"}
        r = subprocess.run([sys.executable, str(REPO / "reconciler" / "gateway_env.py")], capture_output=True,
                           text=True, env={**os.environ, **env, "NOVAK_HOME": str(h.dir)})
        self.assertEqual(r.returncode, 0, r.stderr)
        f = h.dir / "gateway.env"
        text = f.read_text()
        self.assertIn("OUTLINE_EVERYTHING_API_KEY=outline-secret", text)
        self.assertIn("HINDSIGHT_API_KEY=hs-secret", text)
        self.assertNotIn("not-listed-for-anyone", text)
        self.assertNotIn("unrelated", text)
        self.assertNotIn("set-in-keychain", text)                                            # a placeholder is not a secret
        self.assertIn("GATEWAY_HA_TOKEN", r.stderr)                                          # and it says so
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()


class BankTests(unittest.TestCase):
    def test_missing_banks_are_created_and_existing_ones_left_alone(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer
        calls = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _reply(self, obj):
                body = json.dumps(obj).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            def do_GET(self):
                calls.append(("GET", self.path, self.headers["Authorization"]))
                self._reply({"banks": [{"bank_id": "tmeuze"}]})
            def do_PUT(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                calls.append(("PUT", self.path, self.headers["Authorization"]))
                self._reply({"bank_id": "ushy"})

        srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        h = Home(self)
        base = f"http://127.0.0.1:{srv.server_port}"
        reg = yaml.safe_load((h.dir / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"] += [{"name": "hindsight-tmeuze", "kind": "external", "url": f"{base}/mcp/tmeuze/", "auth": "HINDSIGHT_API_KEY", "enabled": True},
                           {"name": "hindsight-ushy", "kind": "external", "url": f"{base}/mcp/ushy/", "auth": "HINDSIGHT_API_KEY", "enabled": True}]
        (h.dir / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        r = h.run("banks", env={"HINDSIGHT_API_KEY": "tenant-key"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Created Hindsight bank 'ushy'", r.stderr)
        puts = [c for c in calls if c[0] == "PUT"]
        self.assertEqual([c[1] for c in puts], ["/v1/default/banks/ushy"])          # tmeuze already existed
        self.assertTrue(all(c[2] == "Bearer tenant-key" for c in calls))

    def test_no_key_means_a_clear_note_and_no_failure(self):
        h = Home(self)
        r = h.run("banks", env={"HINDSIGHT_API_KEY": ""})
        self.assertEqual(r.returncode, 0)


class ExistingBankTests(unittest.TestCase):
    def test_adding_a_person_whose_bank_entry_already_exists_reuses_it(self):
        h = Home(self)
        reg = yaml.safe_load((h.dir / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"].append({"name": "hindsight-ushy", "kind": "external", "url": "http://hs:8888/mcp/ushy/",
                               "auth": "HINDSIGHT_API_KEY", "enabled": True})
        (h.dir / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        r = h.run("add", "ushy", "--yes", "--bank", env={"HINDSIGHT_API_KEY": ""})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Using the existing memory bank entry hindsight-ushy", r.stderr)
        self.assertEqual(h.load()["people"]["ushy"]["entries"], ["hindsight-ushy"])
        self.assertEqual(sum(1 for e in yaml.safe_load((h.dir / "registry" / "mcp-servers.yaml").read_text())["servers"]
                             if e["name"] == "hindsight-ushy"), 1)

    def test_set_changes_emails_and_channel_without_touching_entries_or_key(self):
        h = Home(self)
        h.run("add", "tmeuze", "--yes", "--entries", "tududi-tui")
        before = h.load()["people"]["tmeuze"]
        r = h.run("set", "tmeuze", "--emails", "a@example.com,b@example.com", "--ticker", "Novak")
        self.assertEqual(r.returncode, 0, r.stderr)
        p = h.load()["people"]["tmeuze"]
        self.assertEqual(p["emails"], ["a@example.com", "b@example.com"])
        self.assertEqual(p["notify"], {"kind": "ticker", "category": "Novak"})
        self.assertEqual((p["entries"], p["key_sha256"]), (before["entries"], before["key_sha256"]))
        h.run("set", "tmeuze", "--no-notify")
        self.assertNotIn("notify", h.load()["people"]["tmeuze"])


class GatewayEnvUrlTests(unittest.TestCase):
    def test_a_secret_address_variable_is_passed_to_the_gateway(self):
        h = Home(self)
        reg = yaml.safe_load((h.dir / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"].append({"name": "ha-mcp", "kind": "external", "url_env": "HA_MCP_URL", "enabled": True})
        (h.dir / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        h.run("add", "tmeuze", "--yes", "--entries", "ha-mcp")
        r = subprocess.run([sys.executable, str(REPO / "reconciler" / "gateway_env.py")], capture_output=True, text=True,
                           env={**os.environ, "NOVAK_HOME": str(h.dir), "HA_MCP_URL": "http://x:1/private_zzz"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("HA_MCP_URL=http://x:1/private_zzz", (h.dir / "gateway.env").read_text())
