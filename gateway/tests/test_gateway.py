import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from novak_gateway import directory, policy
from novak_gateway.approvals import Approvals
from novak_gateway.audit import Audit
from novak_gateway.auth import OIDC
from novak_gateway.directory import sha256
from novak_gateway.server import make_server
from novak_gateway.service import Gateway


def fake_backend(tools, name):
    """An MCP server that records what it was asked and with which credential."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def do_POST(self):
            msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((msg.get("method"), self.headers.get("Authorization"), msg.get("params")))
            if "id" not in msg:
                self.send_response(202); self.send_header("Content-Length", "0"); self.end_headers(); return
            m = msg["method"]
            if m == "initialize":
                res = {"protocolVersion": "2025-03-26", "capabilities": {}}
            elif m == "tools/list":
                res = {"tools": [{"name": t, "description": f"{name} {t}", "inputSchema": {"type": "object"}} for t in tools]}
            else:
                res = {"content": [{"type": "text", "text": f"{name} did {msg['params']['name']}"}]}
            body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


class World:
    """Two people, a household, three backends, a gateway, and an HTTP server."""

    def __init__(self, test, oidc=None, notifier=None, confirm_timeout=5, settings=None, helper_reader=None):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.srvs = {}
        self.seen = {}
        for name, tools in {"hs-tmeuze": ["recall", "retain", "delete_document"],
                            "hs-ushy": ["recall", "retain", "delete_document"],
                            "hs-household": ["recall", "retain", "delete_document", "clear_memories"]}.items():
            srv, seen = fake_backend(tools, name)
            test.addCleanup(srv.shutdown)
            self.srvs[name], self.seen[name] = srv, seen
        url = lambda n: f"http://127.0.0.1:{self.srvs[n].server_port}/mcp/"
        self.keys = {"tmeuze": "key-tmeuze-aaaaaaaa", "ushy": "key-ushy-bbbbbbbbb", "household": "key-house-cccccccc",
                     "owui": "key-owui-dddddddddd"}
        servers = [{"name": n, "kind": "external", "url": url(n), "auth": f"TOK_{n.upper().replace('-', '_')}",
                    "enabled": True} for n in self.srvs]
        (self.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": servers}))
        (self.dir / "people.yaml").write_text(yaml.safe_dump({
            "people": {
                "tmeuze": {"names": ["tmeuze"], "emails": ["t@example.com"], "entries": ["hs-tmeuze"],
                           "key_sha256": sha256(self.keys["tmeuze"]),
                           "notify": {"kind": "ticker", "category": "Novak tmeuze"}},
                "ushy": {"names": ["ushy"], "entries": ["hs-ushy"], "key_sha256": sha256(self.keys["ushy"])}},
            "household": {"entries": ["hs-household"], "key_sha256": sha256(self.keys["household"])}}))
        (self.dir / "gateway.yaml").write_text(yaml.safe_dump({"gateway": {
            "confirm_timeout_s": confirm_timeout, "notify_default": {"kind": "ticker", "category": "Novak"},
            "clients": [{"name": "open-webui", "key_sha256": sha256(self.keys["owui"]), "user_header": "X-Novak-User"}],
            **(settings or {})}}))
        self.env = {"TOK_HS_TMEUZE": "backend-secret-tmeuze", "TOK_HS_USHY": "backend-secret-ushy",
                    "TOK_HS_HOUSEHOLD": "backend-secret-house", "GATEWAY_HA_URL": "http://ha", "GATEWAY_HA_TOKEN": "t"}
        self.notes = []
        self.audit = Audit(str(self.dir / "audit.db"))
        self.approvals = Approvals(str(self.dir / "approvals.db"))
        self.gw = Gateway(self.dir, self.audit, self.approvals, "http://gw.test", self.env,
                          notifier=notifier or (lambda *a: self.notes.append(a) or "test"),
                          **({"helper_reader": helper_reader, "helper_poll_s": 0.05} if helper_reader else {}))
        self.server = make_server(self.gw, oidc, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def rpc(self, method, params=None, path="/mcp", token=None, headers=None, mid=1):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        h.update(headers or {})
        body = json.dumps({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}}).encode()
        req = urllib.request.Request(self.base + path, data=body, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def tools(self, **kw):
        code, r = self.rpc("tools/list", **kw)
        return code, [t["name"] for t in r["result"]["tools"]] if code == 200 else r

    def call(self, name, args=None, **kw):
        return self.rpc("tools/call", {"name": name, "arguments": args or {}}, **kw)


class IsolationTests(unittest.TestCase):
    def test_each_person_sees_only_their_own_tools(self):
        w = World(self)
        _, t = w.tools(token=w.keys["tmeuze"])
        self.assertEqual(sorted(t), ["hs_tmeuze__delete_document", "hs_tmeuze__recall", "hs_tmeuze__retain"])
        _, u = w.tools(token=w.keys["ushy"])
        self.assertTrue(all(n.startswith("hs_ushy__") for n in u))

    def test_a_person_cannot_call_anothers_tool_even_by_name(self):
        w = World(self)
        code, r = w.call("hs_tmeuze__recall", token=w.keys["ushy"])
        self.assertTrue(r["result"]["isError"])
        self.assertEqual(w.seen["hs-tmeuze"], [])             # never reached the backend

    def test_backend_gets_the_persons_credential_not_the_callers_key(self):
        w = World(self)
        w.call("hs_ushy__recall", {"query": "x"}, token=w.keys["ushy"])
        auths = {a for m, a, p in w.seen["hs-ushy"] if m == "tools/call"}
        self.assertEqual(auths, {"Bearer backend-secret-ushy"})
        self.assertNotIn(w.keys["ushy"], json.dumps(w.seen))

    def test_household_sees_household_and_never_removals(self):
        w = World(self)
        _, t = w.tools(token=w.keys["household"], path="/mcp/household")
        self.assertEqual(sorted(t), ["hs_household__recall", "hs_household__retain"])
        code, r = w.call("hs_household__clear_memories", path="/mcp/household", token=w.keys["household"])
        self.assertTrue(r["result"]["isError"])
        self.assertEqual([m for m, *_ in w.seen["hs-household"] if m == "tools/call"], [])

    def test_household_key_in_the_url_for_clients_that_cannot_send_headers(self):
        w = World(self)
        code, t = w.tools(path=f"/mcp/household/k/{w.keys['household']}")
        self.assertEqual(code, 200)
        self.assertEqual(sorted(t), ["hs_household__recall", "hs_household__retain"])
        self.assertEqual(w.tools(path="/mcp/household/k/wrong-key-value")[0], 401)
        self.assertEqual(w.tools(path=f"/mcp/household/k/{w.keys['tmeuze']}")[0], 401)   # a person key is not the household's

    def test_a_person_key_does_not_open_the_household_and_vice_versa(self):
        w = World(self)
        self.assertEqual(w.tools(token=w.keys["tmeuze"], path="/mcp/household")[0], 401)
        self.assertEqual(w.tools(token=w.keys["household"])[0], 401)

    def test_a_dead_backend_does_not_hide_the_others(self):
        w = World(self)
        people = yaml.safe_load((w.dir / "people.yaml").read_text())
        people["people"]["tmeuze"]["entries"] = ["hs-tmeuze", "hs-ushy"]
        (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
        w.srvs["hs-ushy"].shutdown(); w.srvs["hs-ushy"].server_close()
        time.sleep(0.05)
        _, t = w.tools(token=w.keys["tmeuze"])
        self.assertIn("hs_tmeuze__recall", t)


class AuthTests(unittest.TestCase):
    def test_no_or_wrong_credential_is_refused(self):
        w = World(self)
        self.assertEqual(w.tools()[0], 401)
        self.assertEqual(w.tools(token="nope")[0], 401)

    def test_path_key_works_for_clients_that_cannot_send_headers(self):
        w = World(self)
        code, t = w.tools(path=f"/mcp/k/{w.keys['ushy']}")
        self.assertEqual(code, 200)
        self.assertTrue(all(n.startswith("hs_ushy__") for n in t))
        self.assertEqual(w.tools(path="/mcp/k/wrong-key-value")[0], 401)

    def test_trusted_client_vouches_for_a_user_by_header(self):
        w = World(self)
        _, t = w.tools(token=w.keys["owui"], headers={"X-Novak-User": "t@example.com"})
        self.assertTrue(all(n.startswith("hs_tmeuze__") for n in t))
        _, t = w.tools(token=w.keys["owui"], headers={"X-Novak-User": "USHY"})
        self.assertTrue(all(n.startswith("hs_ushy__") for n in t))
        self.assertEqual(w.tools(token=w.keys["owui"])[0], 400)                         # no user named
        self.assertEqual(w.tools(token=w.keys["owui"], headers={"X-Novak-User": "stranger"})[0], 403)

    def test_a_person_key_cannot_vouch_for_someone_else_with_the_header(self):
        w = World(self)
        _, t = w.tools(token=w.keys["ushy"], headers={"X-Novak-User": "tmeuze"})
        self.assertTrue(all(n.startswith("hs_ushy__") for n in t))   # the header is ignored

    def test_initialize_says_who_you_are_acting_for(self):
        w = World(self)
        _, r = w.rpc("initialize", token=w.keys["tmeuze"])
        self.assertIn("acting for tmeuze", r["result"]["instructions"])


class PolicyTests(unittest.TestCase):
    def test_real_tool_names(self):
        k = policy.classify
        for t in ("recall", "list_documents", "get_bank", "search_knowledge_base", "reflect", "fetch", "list_tags"):
            self.assertEqual(k(t), "read", t)
        for t in ("retain", "sync_retain", "create_document", "create_task", "add_comment", "create_directive"):
            self.assertEqual(k(t), "append", t)
        for t in ("delete_document", "clear_memories", "invalidate_memory", "cancel_operation",
                  "delete_bank", "delete_mental_model", "delete_knowledge_node", "archive_task", "remove_tag"):
            self.assertEqual(k(t), "destructive", t)
        for t in ("update_document", "move_document", "restore_document", "update_memory", "complete_task",
                  "refresh_mental_model"):
            self.assertEqual(k(t), "modify", t)
        self.assertEqual(k("frobnicate"), "modify")

    def test_overrides_win(self):
        self.assertEqual(policy.classify("recall", {"recall": "destructive"}), "destructive")


class ConfirmTests(unittest.TestCase):
    def test_removal_is_held_until_the_person_approves(self):
        w = World(self)
        out = {}
        th = threading.Thread(target=lambda: out.update(r=w.call("hs_tmeuze__delete_document", {"id": "d1"}, token=w.keys["tmeuze"])))
        th.start()
        for _ in range(50):
            if w.notes:
                break
            time.sleep(0.05)
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])   # nothing yet
        person_notify, default, _, _, title, _, url = w.notes[0]
        self.assertEqual(person_notify, {"kind": "ticker", "category": "Novak tmeuze"})   # their own channel
        self.assertTrue(url.startswith("http://gw.test/approve/"))
        token = url.rsplit("/", 1)[1]
        page = urllib.request.urlopen(f"{w.base}/approve/{token}").read().decode()
        self.assertIn("delete document", page)
        self.assertIn("&quot;id&quot;: &quot;d1&quot;", page)                             # shows what will be removed
        urllib.request.urlopen(urllib.request.Request(f"{w.base}/approve/{token}/approve", data=b"", method="POST"))
        th.join(5)
        code, r = out["r"]
        self.assertEqual(r["result"]["content"][0]["text"], "hs-tmeuze did delete_document")
        self.assertEqual(len([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"]), 1)

    def test_deny_leaves_the_backend_untouched(self):
        w = World(self)
        out = {}
        th = threading.Thread(target=lambda: out.update(r=w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])))
        th.start()
        for _ in range(50):
            if w.notes: break
            time.sleep(0.05)
        token = w.notes[0][6].rsplit("/", 1)[1]
        urllib.request.urlopen(urllib.request.Request(f"{w.base}/approve/{token}/deny", data=b"", method="POST"))
        th.join(5)
        self.assertTrue(out["r"][1]["result"]["isError"])
        self.assertIn("declined", out["r"][1]["result"]["content"][0]["text"])
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])

    def test_silence_expires_without_acting(self):
        w = World(self, confirm_timeout=0.3)
        code, r = w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        self.assertTrue(r["result"]["isError"])
        self.assertIn("No confirmation", r["result"]["content"][0]["text"])
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])

    def test_a_decision_can_only_be_made_once(self):
        w = World(self, confirm_timeout=0.3)
        w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        token = w.notes[0][6].rsplit("/", 1)[1]
        a = w.approvals.by_token(token)
        self.assertEqual(a["status"], "expired")
        self.assertFalse(w.approvals.decide(a["id"], True))                               # too late

    def test_appending_is_immediate_and_needs_no_confirmation(self):
        w = World(self)
        code, r = w.call("hs_tmeuze__retain", {"content": "x"}, token=w.keys["tmeuze"])
        self.assertEqual(r["result"]["content"][0]["text"], "hs-tmeuze did retain")
        self.assertEqual(w.notes, [])


class AuditTests(unittest.TestCase):
    def test_accounting_records_who_and_what_but_not_the_values(self):
        w = World(self)
        w.call("hs_ushy__retain", {"content": "my secret diary entry"}, token=w.keys["ushy"])
        w.call("hs_tmeuze__recall", token=w.keys["ushy"])                                  # not theirs
        rows = w.audit.recent()
        dump = json.dumps(rows)
        self.assertNotIn("secret diary", dump)
        ok = [r for r in rows if r["tool"] == "retain"][0]
        self.assertEqual((ok["person"], ok["via"], ok["entry"], ok["kind"], ok["decision"], ok["outcome"]),
                         ("ushy", "key", "hs-ushy", "append", "allowed", "ok"))
        self.assertEqual(json.loads(ok["arg_names"]), ["content"])
        self.assertTrue(any(r["decision"] == "denied" for r in rows))


class DirectoryTests(unittest.TestCase):
    def test_validate_flags_a_personal_entry_shared_by_two_people(self):
        w = World(self)
        people = yaml.safe_load((w.dir / "people.yaml").read_text())
        people["people"]["ushy"]["entries"].append("hs-tmeuze")
        (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
        problems = directory.validate(directory.load(w.dir))
        self.assertTrue(any("one credential, several people" in p for p in problems))

    def test_two_people_cannot_claim_the_same_name(self):
        w = World(self)
        people = yaml.safe_load((w.dir / "people.yaml").read_text())
        people["people"]["ushy"]["names"].append("tmeuze")
        (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
        with self.assertRaises(directory.ConfigError):
            directory.load(w.dir)

    def test_config_changes_are_picked_up_without_a_restart(self):
        w = World(self)
        self.assertEqual(w.tools(token=w.keys["ushy"])[0], 200)
        people = yaml.safe_load((w.dir / "people.yaml").read_text())
        del people["people"]["ushy"]
        time.sleep(0.01)
        (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
        import os
        os.utime(w.dir / "people.yaml", (time.time() + 5, time.time() + 5))
        self.assertEqual(w.tools(token=w.keys["ushy"])[0], 401)


class NotifyTests(unittest.TestCase):
    def test_channels(self):
        from novak_gateway import notify
        sent = []
        post = lambda url, tok, path, body: sent.append((path, body))
        self.assertIn("ticker", notify.send({"kind": "ticker", "category": "C"}, {}, "http://ha", "t", "T", "M", "http://u", post))
        self.assertEqual(sent[0][0], "/api/services/ticker/notify")
        self.assertEqual(sent[0][1]["data"]["url"], "http://u")
        notify.send({"kind": "ha", "service": "notify.mobile_app_p"}, {}, "http://ha", "t", "T", "M", "http://u", post)
        self.assertEqual(sent[1][0], "/api/services/notify/mobile_app_p")
        self.assertEqual(notify.send({}, {}, "http://ha", "t", "T", "M", "u", post), "no notification channel configured")
        notify.send({}, {"kind": "ticker", "category": "Novak"}, "http://ha", "t", "T", "M", "u", post)   # default
        self.assertEqual(sent[2][1]["category"], "Novak")


if __name__ == "__main__":
    unittest.main()


class FilterTests(unittest.TestCase):
    def filters(self, w, filters):
        g = yaml.safe_load((w.dir / "gateway.yaml").read_text())
        g["gateway"]["tool_filters"] = filters
        (w.dir / "gateway.yaml").write_text(yaml.safe_dump(g))
        import os
        os.utime(w.dir / "gateway.yaml", (time.time() + 5, time.time() + 5))

    def test_allow_list_limits_what_is_offered_and_callable(self):
        w = World(self)
        self.filters(w, [{"entries": "hs-*", "allow": ["recall", "delete_*"]}])
        _, t = w.tools(token=w.keys["tmeuze"])
        self.assertEqual(sorted(t), ["hs_tmeuze__delete_document", "hs_tmeuze__recall"])
        code, r = w.call("hs_tmeuze__retain", {"content": "x"}, token=w.keys["tmeuze"])      # hidden means not callable
        self.assertTrue(r["result"]["isError"])
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])

    def test_deny_removes_tools_and_unmatched_entries_are_untouched(self):
        w = World(self)
        self.filters(w, [{"entries": "hs-tmeuze", "deny": ["delete_*"]}])
        _, t = w.tools(token=w.keys["tmeuze"])
        self.assertNotIn("hs_tmeuze__delete_document", t)
        _, u = w.tools(token=w.keys["ushy"])
        self.assertIn("hs_ushy__delete_document", u)

    def test_unit(self):
        f = [{"entries": "a-*", "allow": ["x"]}, {"entries": "*", "deny": ["y"]}]
        self.assertTrue(directory.tool_allowed(f, "a-1", "x"))
        self.assertFalse(directory.tool_allowed(f, "a-1", "z"))
        self.assertFalse(directory.tool_allowed(f, "b-1", "y"))   # first match decides
        self.assertTrue(directory.tool_allowed(f, "b-1", "z"))
        self.assertTrue(directory.tool_allowed([], "anything", "anything"))

    def test_the_shipped_defaults_keep_the_useful_tools(self):
        from pathlib import Path as P
        shipped = yaml.safe_load((P(__file__).resolve().parents[2] / "registry" / "gateway.yaml").read_text())["gateway"]["tool_filters"]
        for tool in ("recall", "retain", "reflect", "delete_document"):
            self.assertTrue(directory.tool_allowed(shipped, "hindsight-tmeuze", tool), tool)
        for tool in ("delete_bank", "clear_memories", "update_bank", "create_directive", "cancel_operation"):
            self.assertFalse(directory.tool_allowed(shipped, "hindsight-tmeuze", tool), tool)
        for tool in ("create_document", "list_collections", "delete_document"):
            self.assertTrue(directory.tool_allowed(shipped, "outline-everything", tool), tool)
        self.assertFalse(directory.tool_allowed(shipped, "outline-everything", "delete_collection"))
        for tool in ("create_task", "list_tasks", "complete_task", "delete_task", "add_to_inbox", "search"):
            self.assertTrue(directory.tool_allowed(shipped, "tududi-tui", tool), tool)
        for tool in ("create_habit", "delete_person", "create_view", "create_goal"):
            self.assertFalse(directory.tool_allowed(shipped, "tududi-tui", tool), tool)
        n = sum(directory.tool_allowed(shipped, "tududi-tui", t) for t in (
            "list_tasks get_task create_task update_task complete_task delete_task add_subtask add_task_comment "
            "list_task_comments get_task_metrics list_projects get_project create_project update_project delete_project "
            "list_areas list_tags create_tag list_notes get_note create_note update_note delete_note add_to_inbox "
            "list_inbox process_inbox_item search create_habit create_goal create_view delete_person").split())
        self.assertEqual(n, 27)


class NotifyErrorTests(unittest.TestCase):
    def test_home_assistant_refusal_reason_is_reported(self):
        from novak_gateway import notify
        srv = HTTPServer(("127.0.0.1", 0), type("H", (BaseHTTPRequestHandler,), {
            "log_message": lambda *a: None,
            "do_POST": lambda s: (s.rfile.read(int(s.headers["Content-Length"])), s.send_response(400),
                                  s.send_header("Content-Length", "50"), s.end_headers(),
                                  s.wfile.write(b'{"message":"Category Novak not found. Check it"}  '))[0]}))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        with self.assertRaises(RuntimeError) as cm:
            notify._post(f"http://127.0.0.1:{srv.server_port}", "t", "/x", {})
        self.assertIn("Category Novak not found", str(cm.exception))


class UrlEnvTests(unittest.TestCase):
    def world_with_secret_url(self, w):
        servers = yaml.safe_load((w.dir / "mcp-servers.yaml").read_text())
        for s in servers["servers"]:
            if s["name"] == "hs-ushy":
                s.pop("url")
                s["url_env"] = "HS_USHY_URL"
        (w.dir / "mcp-servers.yaml").write_text(yaml.safe_dump(servers))
        import os
        os.utime(w.dir / "mcp-servers.yaml", (time.time() + 5, time.time() + 5))

    def test_the_address_comes_from_the_environment_not_the_registry(self):
        w = World(self)
        real_url = f"http://127.0.0.1:{w.srvs['hs-ushy'].server_port}/mcp/"
        self.world_with_secret_url(w)
        w.env["HS_USHY_URL"] = real_url
        _, t = w.tools(token=w.keys["ushy"])
        self.assertTrue(t and all(n.startswith("hs_ushy__") for n in t))
        self.assertNotIn(real_url, (w.dir / "mcp-servers.yaml").read_text())

    def test_an_unset_address_is_reported_not_guessed(self):
        w = World(self)
        self.world_with_secret_url(w)
        code, t = w.tools(token=w.keys["ushy"])
        self.assertEqual((code, t), (200, []))                       # the entry is skipped, nothing crashes
        self.assertTrue(any("address of hs-ushy (HS_USHY_URL) is not set" in r["outcome"] for r in w.audit.recent()))


class HaMcpFilterTests(unittest.TestCase):
    def shipped(self):
        from pathlib import Path as P
        return yaml.safe_load((P(__file__).resolve().parents[2] / "registry" / "gateway.yaml").read_text())["gateway"]

    def test_the_shipped_filter_offers_lookups_and_devices_but_not_configuration(self):
        f = self.shipped()["tool_filters"]
        for tool in ("ha_search", "ha_get_state", "ha_call_service", "ha_bulk_control", "ha_get_history", "ha_set_todo_item"):
            self.assertTrue(directory.tool_allowed(f, "ha-mcp", tool), tool)
        for tool in ("ha_restart", "ha_manage_backup", "ha_manage_updates", "ha_config_set_automation", "ha_config_remove_script",
                     "ha_eval_template", "ha_remove_device", "ha_reload_core", "ha_manage_hacs", "ha_get_logs"):
            self.assertFalse(directory.tool_allowed(f, "ha-mcp", tool), tool)

    def test_acting_on_a_device_needs_a_tap_and_lookups_do_not(self):
        from novak_gateway import policy
        ov = self.shipped()["tool_overrides"]["ha-mcp"]
        self.assertEqual(policy.classify("ha_call_service", ov), "destructive")
        self.assertEqual(policy.classify("ha_bulk_control", ov), "destructive")
        self.assertEqual(policy.classify("ha_search", ov), "read")
        self.assertEqual(policy.classify("ha_remove_todo_item", ov), "destructive")      # removals are held anyway


class ButtonTests(unittest.TestCase):
    """Approve and Deny buttons on the phone: Home Assistant writes the pressed action into a helper."""
    HELPER = {"approval_helper": "input_text.novak_approval"}

    def world(self, press, **kw):
        w = World(self, confirm_timeout=3, settings=dict(self.HELPER, **kw.pop("settings", {})),
                  helper_reader=lambda url, tok, ent: press(w))
        return w

    def token(self, w):
        return w.notes[0][6].rsplit("/", 1)[1] if w.notes else None

    def test_a_pressed_approve_runs_the_held_call(self):
        w = self.world(lambda w: f"NOVAK_APPROVE_{self.token(w)}" if w.notes else "")
        _, r = w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        self.assertEqual(r["result"]["content"][0]["text"], "hs-tmeuze did delete_document")

    def test_the_link_is_dropped_only_when_buttons_are_on_and_only_for_ha_channels(self):
        ha = {"notify_default": {"kind": "ha", "service": "mobile_app_x"}}
        w = World(self, confirm_timeout=0.3, settings=dict(self.HELPER, **ha), helper_reader=lambda *a: "")
        w.call("hs_ushy__delete_document", token=w.keys["ushy"])               # ushy has no channel of their own
        self.assertEqual(w.notes[0][1], {"kind": "ha", "service": ["mobile_app_x"], "link": False})   # (person, default, ...)
        w = World(self, confirm_timeout=0.3, settings=ha)                      # no helper: the link is all there is
        w.call("hs_ushy__delete_document", token=w.keys["ushy"])
        self.assertEqual(w.notes[0][1], {"kind": "ha", "service": ["mobile_app_x"], "link": True})
        w = World(self, confirm_timeout=0.3, settings=self.HELPER, helper_reader=lambda *a: "")
        w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])           # Ticker is passed through untouched
        self.assertEqual(w.notes[0][0], {"kind": "ticker", "category": "Novak tmeuze"})

    def test_a_pressed_deny_does_nothing(self):
        w = self.world(lambda w: f"NOVAK_DENY_{self.token(w)}" if w.notes else "")
        _, r = w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        self.assertTrue(r["result"]["isError"])
        self.assertIn("declined", r["result"]["content"][0]["text"])
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])

    def test_an_old_or_foreign_action_is_ignored(self):
        w = self.world(lambda w: "NOVAK_APPROVE_somebody-elses-token", )
        w.gw.dir.settings["confirm_timeout_s"] = 0.4
        _, r = w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        self.assertIn("No confirmation", r["result"]["content"][0]["text"])
        self.assertEqual([m for m, *_ in w.seen["hs-tmeuze"] if m == "tools/call"], [])

    def test_a_helper_that_cannot_be_read_does_not_break_the_wait(self):
        def broken(w):
            raise OSError("ha down")
        w = self.world(broken)
        w.gw.dir.settings["confirm_timeout_s"] = 0.4
        _, r = w.call("hs_tmeuze__delete_document", token=w.keys["tmeuze"])
        self.assertIn("No confirmation", r["result"]["content"][0]["text"])

    def test_the_notification_carries_the_buttons_and_reaches_every_phone_in_the_group(self):
        from novak_gateway import notify
        sent = []
        post = lambda url, tok, path, body: sent.append((path, body))
        cfg = notify.expand({"kind": "ha", "service": "mgmt"}, {"mgmt": ["mobile_app_pyrite", "mobile_app_aquarius"]})
        out = notify.send(cfg, {}, "http://ha", "t", "Confirm: x", "m", "http://gw/approve/TOK123", post)
        self.assertEqual([p for p, _ in sent], ["/api/services/notify/mobile_app_pyrite", "/api/services/notify/mobile_app_aquarius"])
        actions = sent[0][1]["data"]["actions"]
        self.assertEqual([a["action"] for a in actions[:2]], ["NOVAK_APPROVE_TOK123", "NOVAK_DENY_TOK123"])
        self.assertIn("clickAction", sent[0][1]["data"])                                # a link unless told not to
        sent.clear()
        notify.send(dict(cfg, link=False), {}, "http://ha", "t", "T", "m", "http://gw/approve/TOK123", post)
        data = sent[0][1]["data"]
        self.assertNotIn("clickAction", data)
        self.assertNotIn("url", data)
        self.assertEqual(len(data["actions"]), 2)                                       # buttons only
        self.assertIn("pyrite", out)
        self.assertIn("aquarius", out)

    def test_one_phone_failing_does_not_hide_the_other(self):
        from novak_gateway import notify
        def post(url, tok, path, body):
            if "pyrite" in path:
                raise RuntimeError("offline")
        out = notify.send({"kind": "ha", "service": ["mobile_app_pyrite", "mobile_app_aquarius"]}, {}, "http://ha", "t",
                          "T", "M", "http://gw/approve/TOK", post)
        self.assertIn("aquarius", out)
        with self.assertRaises(RuntimeError):
            notify.send({"kind": "ha", "service": ["mobile_app_pyrite"]}, {}, "http://ha", "t", "T", "M", "http://gw/approve/TOK", post)


class ArgRuleTests(unittest.TestCase):
    """A held tool lets harmless calls through, judged by the call's own arguments."""
    RULE = {"to": "modify", "allow": {"light": ["turn_on", "turn_off"], "scene": ["turn_on"]}}

    def shipped_rule(self, tool="ha_call_service"):
        from pathlib import Path as P
        g = yaml.safe_load((P(__file__).resolve().parents[2] / "registry" / "gateway.yaml").read_text())["gateway"]
        return g["arg_rules"]["ha-mcp"][tool]

    def test_a_listed_domain_and_service_passes_and_everything_else_does_not(self):
        from novak_gateway.policy import relaxed
        r = self.shipped_rule()
        self.assertTrue(relaxed(r, {"domain": "light", "service": "turn_on", "data": {"rgb_color": [255, 0, 128]}}))
        self.assertTrue(relaxed(r, {"domain": "light", "service": "turn_on", "entity_id": "light.a, light.b"}))
        self.assertTrue(relaxed(r, {"domain": "scene", "service": "turn_on", "entity_id": "scene.movie"}))
        self.assertFalse(relaxed(r, {"domain": "lock", "service": "unlock", "entity_id": "lock.front"}))
        self.assertFalse(relaxed(r, {"domain": "light", "service": "delete"}))
        self.assertFalse(relaxed(r, {"domain": "light", "service": "turn_on", "entity_id": "lock.front"}))   # target in another domain
        self.assertFalse(relaxed(r, {"domain": "light", "service": "turn_on", "ws_command": "config/entity_registry/remove"}))
        self.assertFalse(relaxed(r, {"service": "turn_on"}))                                  # no domain
        self.assertFalse(relaxed(r, {}))
        self.assertFalse(relaxed(None, {"domain": "light", "service": "turn_on"}))
        self.assertFalse(relaxed({"allow": {}}, {"domain": "light", "service": "turn_on"}))

    def test_bulk_control_needs_every_operation_to_be_harmless(self):
        from novak_gateway.policy import relaxed
        r = self.shipped_rule("ha_bulk_control")
        ok = [{"entity_id": "light.a", "action": "on", "parameters": {"brightness_pct": 30}}, {"entity_id": "light.b", "action": "off"}]
        self.assertTrue(relaxed(r, {"operations": ok}))
        self.assertFalse(relaxed(r, {"operations": ok + [{"entity_id": "lock.front", "action": "off"}]}))
        self.assertFalse(relaxed(r, {"operations": [{"entity_id": "light.a", "action": "delete"}]}))

    def test_through_the_gateway_a_harmless_call_runs_and_a_risky_one_is_held(self):
        w = World(self, confirm_timeout=0.3, settings={"arg_rules": {"hs-tmeuze": {"delete_document": self.RULE}}})
        _, r = w.call("hs_tmeuze__delete_document", {"domain": "light", "service": "turn_on"}, token=w.keys["tmeuze"])
        self.assertEqual(r["result"]["content"][0]["text"], "hs-tmeuze did delete_document")
        self.assertEqual(w.notes, [])                                                       # no approval was asked for
        _, r = w.call("hs_tmeuze__delete_document", {"domain": "lock", "service": "unlock"}, token=w.keys["tmeuze"])
        self.assertTrue(r["result"]["isError"])
        self.assertIn("No confirmation", r["result"]["content"][0]["text"])
        self.assertEqual(len(w.notes), 1)

    def test_a_harmless_call_is_fine_for_the_household_too(self):
        w = World(self, settings={"arg_rules": {"hs-household": {"delete_document": self.RULE}}})
        _, r = w.call("hs_household__delete_document", {"domain": "light", "service": "turn_on"},
                       token=w.keys["household"], path="/mcp/household")
        self.assertEqual(r["result"]["content"][0]["text"], "hs-household did delete_document")   # a lamp is a lamp
        _, r = w.call("hs_household__delete_document", {"domain": "lock", "service": "unlock"},
                      token=w.keys["household"], path="/mcp/household")
        self.assertTrue(r["result"]["isError"])                                              # still needs a person to confirm


class AccountOwnershipTests(unittest.TestCase):
    def test_an_entry_that_names_its_user_cannot_be_given_to_someone_else(self):
        w = World(self)
        servers = yaml.safe_load((w.dir / "mcp-servers.yaml").read_text())
        for s in servers["servers"]:
            if s["name"] == "hs-ushy":
                s["user"] = "ushy"
        (w.dir / "mcp-servers.yaml").write_text(yaml.safe_dump(servers))
        self.assertEqual(directory.validate(directory.load(w.dir)), [])
        people = yaml.safe_load((w.dir / "people.yaml").read_text())
        people["people"]["tmeuze"]["entries"].append("hs-ushy")
        people["people"]["ushy"]["entries"].remove("hs-ushy")
        (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
        problems = directory.validate(directory.load(w.dir))
        self.assertTrue(any("is ushy's account, not tmeuze's" in p for p in problems), problems)

    def test_a_personal_account_cannot_be_household(self):
        w = World(self)
        servers = yaml.safe_load((w.dir / "mcp-servers.yaml").read_text())
        for s in servers["servers"]:
            if s["name"] == "hs-household":
                s["user"] = "ushy"
        (w.dir / "mcp-servers.yaml").write_text(yaml.safe_dump(servers))
        self.assertTrue(any("cannot be shared with the household" in p for p in directory.validate(directory.load(w.dir))))
