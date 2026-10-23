import copy
import io
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "reconciler"))
import owui_apply  # noqa: E402

ADMIN = "admin-key-xxxxxxxx"
GATEWAY_KEY = "gateway-key-yyyyyyyy"


class FakeOwui(BaseHTTPRequestHandler):
    """Enough of Open WebUI's admin API: connections are replaced wholesale on POST,
    a model update replaces its meta and params, and everything wants the admin key."""
    state = {}

    def log_message(self, *a):
        pass

    def reply(self, code, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def authorised(self):
        ok = self.headers.get("Authorization") == f"Bearer {ADMIN}"
        if not ok:
            self.reply(401, {"detail": "no"})
        return ok

    def do_GET(self):
        if not self.authorised():
            return
        st = type(self).state
        if self.path == "/api/v1/configs/tool_servers":
            return self.reply(200, {"TOOL_SERVER_CONNECTIONS": st["connections"]})
        if self.path.startswith("/api/v1/models/model?id="):
            m = st["models"].get(self.path.split("=", 1)[1])
            return self.reply(200, m) if m else self.reply(404, {"detail": "not found"})
        self.reply(404)

    def do_POST(self):
        if not self.authorised():
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        st = type(self).state
        st["posts"].append((self.path, body))
        if self.path == "/api/v1/configs/tool_servers":
            st["connections"] = body["TOOL_SERVER_CONNECTIONS"]
            return self.reply(200, body)
        if self.path == "/api/v1/models/create":
            st["models"][body["id"]] = body
            return self.reply(200, body)
        if self.path == "/api/v1/models/model/update":
            old = st["models"][body["id"]]
            st["models"][body["id"]] = {**old, **body, "access_grants": old.get("access_grants")}   # grants untouched
            return self.reply(200, body)
        self.reply(404)


class OwuiApplyTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "prompts").mkdir()
        (self.dir / "prompts" / "persona.md").write_text("# Persona\nintro\n\n---\n\nYou are Novak.\n")
        (self.dir / "prompts" / "tools.md").write_text("# Tools\nintro\n\n---\n\nUse tools honestly.\n")
        self.file = self.dir / "openwebui.yaml"
        self.file.write_text(yaml.safe_dump({"openwebui": {
            "tool_servers": [{"id": "novak-gateway", "name": "Novak gateway", "description": "d", "type": "mcp",
                              "url": "http://gateway:8000/mcp", "auth_type": "bearer", "key_env": "OWUI_GATEWAY_KEY",
                              "headers": {"X-Novak-User": "{{USER_EMAIL}}"}}],
            "models": [{"id": "chat", "tools": ["novak-gateway"], "system_files": ["prompts/persona.md", "prompts/tools.md"]}]}}))
        FakeOwui.state = {"connections": [], "models": {}, "posts": []}
        srv = HTTPServer(("127.0.0.1", 0), FakeOwui)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.env = {"OWUI_ADMIN_API_KEY": ADMIN, "OWUI_GATEWAY_KEY": GATEWAY_KEY,
                    "OWUI_URL": f"http://127.0.0.1:{srv.server_port}", "NOVAK_HOME": str(self.dir)}
        # prompts resolve against the repo in production; point the module at the fixtures
        self._repo = owui_apply.REPO
        owui_apply.REPO = self.dir
        self.addCleanup(lambda: setattr(owui_apply, "REPO", self._repo))

    def run_main(self, *argv, env=None):
        out = io.StringIO()
        code = owui_apply.main(["--file", str(self.file), *argv], env=env or self.env, out=lambda m="": out.write(m + "\n"))
        return code, out.getvalue()

    def existing_chat(self, **kw):
        return {"id": "chat", "name": "chat", "base_model_id": None, "is_active": True,
                "meta": {"description": "mine", "capabilities": {"vision": True}}, "params": {"temperature": 0.2},
                "access_grants": [{"principal_id": "group-1"}], **kw}

    def test_a_fresh_open_webui_gets_the_connection_and_the_preset(self):
        code, out = self.run_main("--apply")
        self.assertEqual(code, 0)
        st = FakeOwui.state
        conn = st["connections"][0]
        self.assertEqual((conn["url"], conn["type"], conn["key"], conn["info"]["id"]),
                         ("http://gateway:8000/mcp", "mcp", GATEWAY_KEY, "novak-gateway"))
        self.assertEqual(conn["headers"], {"X-Novak-User": "{{USER_EMAIL}}"})
        chat = st["models"]["chat"]
        self.assertEqual(chat["meta"]["toolIds"], ["server:mcp:novak-gateway"])
        self.assertEqual(chat["params"]["system"], "You are Novak.\n\nUse tools honestly.")     # headers stripped, files joined
        self.assertNotIn(GATEWAY_KEY, out)                                                        # never printed

    def test_a_second_run_changes_nothing(self):
        self.run_main("--apply")
        FakeOwui.state["posts"].clear()
        code, out = self.run_main("--apply")
        self.assertEqual((code, FakeOwui.state["posts"]), (0, []))
        self.assertIn("matches the file", out)

    def test_the_default_run_only_reports_and_exits_nonzero_on_drift(self):
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(FakeOwui.state["posts"], [])
        self.assertIn("add", out)
        self.assertIn("--apply", out)

    def test_other_connections_survive_and_a_preset_keeps_its_other_settings(self):
        other = {"url": "http://other", "path": "", "type": "openapi", "auth_type": "none", "key": None, "config": {}, "info": {"id": "other", "name": "Other"}}
        FakeOwui.state["connections"] = [copy.deepcopy(other)]
        FakeOwui.state["models"]["chat"] = self.existing_chat()
        self.run_main("--apply")
        st = FakeOwui.state
        self.assertEqual([c["info"]["id"] for c in st["connections"]], ["other", "novak-gateway"])
        chat = st["models"]["chat"]
        self.assertEqual(chat["meta"]["description"], "mine")
        self.assertEqual(chat["meta"]["capabilities"], {"vision": True})
        self.assertEqual(chat["params"]["temperature"], 0.2)
        self.assertEqual(chat["access_grants"], [{"principal_id": "group-1"}])
        self.assertIn("server:mcp:novak-gateway", chat["meta"]["toolIds"])

    def test_a_tool_someone_else_switched_on_stays_on(self):
        FakeOwui.state["models"]["chat"] = self.existing_chat(meta={"toolIds": ["server:mcp:other"]})
        self.run_main("--apply")
        self.assertEqual(FakeOwui.state["models"]["chat"]["meta"]["toolIds"], ["server:mcp:other", "server:mcp:novak-gateway"])

    def test_without_a_key_value_the_existing_key_is_kept(self):
        self.run_main("--apply")
        env = {k: v for k, v in self.env.items() if k != "OWUI_GATEWAY_KEY"}
        FakeOwui.state["posts"].clear()
        code, _ = self.run_main("--apply", env=env)
        self.assertEqual(FakeOwui.state["posts"], [])
        FakeOwui.state["connections"][0]["url"] = "http://stale"
        self.run_main("--apply", env=env)
        self.assertEqual(FakeOwui.state["connections"][0]["key"], GATEWAY_KEY)               # not blanked

    def test_a_changed_key_is_detected_without_printing_it(self):
        self.run_main("--apply")
        env = dict(self.env, OWUI_GATEWAY_KEY="a-new-key-zzzzzzzz")
        code, out = self.run_main(env=env)
        self.assertEqual(code, 1)
        self.assertIn("key differs", out)
        self.assertNotIn("a-new-key-zzzzzzzz", out)
        self.assertNotIn(GATEWAY_KEY, out)

    def test_drift_names_a_changed_system_prompt_and_a_missing_tool(self):
        FakeOwui.state["connections"] = []
        self.run_main("--apply")
        FakeOwui.state["models"]["chat"]["params"]["system"] = "edited by hand"
        FakeOwui.state["models"]["chat"]["meta"]["toolIds"] = []
        code, out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("system prompt updated", out)
        self.assertIn("default tools: server:mcp:novak-gateway on", out)

    def test_a_wrong_admin_key_fails_clearly_before_changing_anything(self):
        code, out = self.run_main("--apply", env=dict(self.env, OWUI_ADMIN_API_KEY="wrong-key-aaaaaaaa"))
        self.assertEqual(code, 2)
        self.assertEqual(FakeOwui.state["posts"], [])

    def test_a_missing_admin_key_says_how_to_make_one(self):
        env = {k: v for k, v in self.env.items() if k != "OWUI_ADMIN_API_KEY"}
        code = owui_apply.main(["--file", str(self.file)], env=env, out=lambda *a: None)
        self.assertEqual(code, 2)

    def test_the_file_is_validated_before_anything_is_sent(self):
        bad = yaml.safe_load(self.file.read_text())
        bad["openwebui"]["models"][0]["tools"] = ["not-a-server"]
        self.file.write_text(yaml.safe_dump(bad))
        self.assertEqual(self.run_main("--apply")[0], 2)
        bad["openwebui"]["models"][0]["tools"] = ["novak-gateway"]
        bad["openwebui"]["tool_servers"][0]["key"] = "pasted-secret"
        self.file.write_text(yaml.safe_dump(bad))
        self.assertEqual(self.run_main("--apply")[0], 2)
        bad["openwebui"]["tool_servers"][0].pop("key")
        bad["openwebui"]["models"][0]["system_files"] = ["prompts/missing.md"]
        self.file.write_text(yaml.safe_dump(bad))
        self.assertEqual(self.run_main("--apply")[0], 2)
        self.assertEqual(FakeOwui.state["posts"], [])

    def test_the_shipped_template_is_valid_and_its_prompts_exist(self):
        cfg = owui_apply.load_config(REPO / "registry" / "openwebui.yaml")
        for m in cfg["models"]:
            self.assertTrue(owui_apply.system_prompt(m, REPO))
        self.assertEqual({m["id"] for m in cfg["models"]}, {"chat", "deep"})


if __name__ == "__main__":
    unittest.main()
