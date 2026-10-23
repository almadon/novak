import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from novak_ingest import idle
from novak_ingest.api import make_server
from novak_ingest.config import DEFAULTS, Settings, _merge
from novak_ingest.store import Store
from novak_ingest.worker import Worker
from test_units import FakeMCP
from http.server import BaseHTTPRequestHandler, HTTPServer

RESULT = json.dumps({
    "title": "Plan the move", "summary": "They discussed moving house.",
    "key_points": ["Movers booked"], "decisions": ["Move on the 3rd"], "people": ["Sam"],
    "tasks": [{"title": "Call Sam about the keys", "detail": "before Friday", "due": "2026-10-16"},
              {"title": "Cancel the internet", "detail": "", "due": None}]})


class Env:
    def __init__(self, test, sinks=None, busy=False):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        cfg = _merge(__import__("copy").deepcopy(DEFAULTS), {"sinks": sinks or []})   # tests edit cfg in place
        self.settings = Settings(
            data=self.dir, token="secret", public_url="http://spire:13409", stt_url="http://stt",
            llm_base_url="http://router", llm_api_key="none", ollama_url="http://ollama",
            keep_alive_s=86400, ha_url="http://ha", ha_token="t", ha_target="mobile_app_x",
            ticker_category="general",
            max_upload_mb=1, cfg=cfg)
        self.store = Store(str(self.dir / "db.sqlite"))
        self.busy = busy
        self.calls = {"analyse": 0, "transcribe": [], "chat": 0, "notify": []}
        self.fail_chunk = None
        self.stopped = False
        self.clock = [1000.0]
        self.gate = idle.IdleGate(lambda: [999.0] if self.busy else [], 180, 1,
                                  clock=lambda: self.clock[0], sleep=lambda s: None)

        def analyse(path):
            self.calls["analyse"] += 1
            return 130.0, [(60.0, 61.0)]

        def extract(audio, start, end, out):
            out.write_bytes(b"RIFF")
            self.last_extract = (start, end)

        def transcribe(url, path, wav, language, extra):
            self.calls["transcribe"].append(self.last_extract)
            if self.fail_chunk is not None and len(self.calls["transcribe"]) == self.fail_chunk:
                raise RuntimeError("stt down")
            return [{"start": 1.0, "end": 3.0, "text": f"hello from {self.last_extract[0]:.0f}"}]

        def chat(base, key, model, messages, json_mode=False, **kw):
            self.calls["chat"] += 1
            return RESULT

        self.worker = Worker(self.settings, self.store, self.gate, lambda: self.stopped,
                             log=lambda m: None, analyse=analyse, extract=extract,
                             transcribe=transcribe, chat=chat,
                             notify_fn=lambda *a: self.calls["notify"].append(a))
        self.server = make_server(self.settings, self.store, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        test.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def req(self, method, path, body=None, headers=None, token="secret"):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        h.update(headers or {})
        r = urllib.request.Request(self.base + path, data=body, method=method, headers=h)
        try:
            with urllib.request.urlopen(r) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if resp.headers["Content-Type"] == "application/json" else raw.decode())
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw.decode()

    def upload(self, data=b"audio-bytes", **headers):
        return self.req("POST", "/v1/recordings", data,
                        {"X-Source": "omi", "X-Filename": "a.opus", "X-Recorded-At": "1760000000", **headers})


class PipelineTests(unittest.TestCase):
    def test_upload_to_done_with_proposals_and_notification(self):
        e = Env(self)
        code, body = e.upload()
        self.assertEqual((code, body["duplicate"]), (201, False))
        self.assertTrue(e.worker.run_once())
        rec = e.store.recording(body["id"])
        self.assertEqual((rec["status"], rec["title"]), ("done", "Plan the move"))
        self.assertEqual(e.calls["transcribe"], [(0.0, 60.5), (60.5, 130.0)])
        note = Path(rec["note_path"]).read_text()
        self.assertIn("Move on the 3rd", note)
        self.assertIn("[00:01:01] hello from 60", note)   # chunk offset applied to timestamps
        props = e.store.proposals("pending")
        self.assertEqual([p["title"] for p in props], ["Call Sam about the keys", "Cancel the internet"])
        self.assertEqual(len(e.calls["notify"]), 1)
        self.assertIn(f"/review/{props[0]['token']}", e.calls["notify"][0][5])
        self.assertFalse(e.worker.run_once())            # nothing left

    def test_duplicate_upload_is_not_queued_twice(self):
        e = Env(self)
        e.upload()
        code, body = e.upload()
        self.assertEqual((code, body["duplicate"]), (200, True))
        self.assertEqual(len(e.store.recordings()), 1)

    def test_api_requires_token_and_validates_input(self):
        e = Env(self)
        self.assertEqual(e.req("GET", "/v1/recordings", token=None)[0], 401)
        self.assertEqual(e.req("GET", "/v1/recordings", token="wrong")[0], 401)
        self.assertEqual(e.upload(**{"X-Recorded-At": "not a date"})[0], 400)
        self.assertEqual(e.req("POST", "/v1/recordings", b"", None)[0], 400)
        self.assertEqual(e.req("POST", "/v1/recordings", b"x" * (1024 * 1024 + 1))[0], 413)
        self.assertEqual(e.req("GET", "/healthz", token=None)[0], 200)

    def test_backseat_nothing_runs_while_models_are_in_use(self):
        e = Env(self, busy=True)
        _, body = e.upload()
        e.stopped = True                     # gate.wait() gives up instead of blocking
        self.assertFalse(e.worker.run_once())
        self.assertEqual((e.calls["analyse"], e.calls["transcribe"], e.calls["chat"]), (0, [], 0))
        self.assertEqual(e.store.recording(body["id"])["status"], "queued")
        e.busy, e.stopped = False, False     # someone stopped chatting
        self.assertTrue(e.worker.run_once())
        self.assertEqual(e.store.recording(body["id"])["status"], "done")

    def test_a_restart_resumes_without_redoing_finished_chunks(self):
        e = Env(self)
        _, body = e.upload()
        e.fail_chunk = 2
        e.worker.run_once()
        rec = e.store.recording(body["id"])
        self.assertEqual((rec["status"], rec["attempts"]), ("queued", 1))
        e.worker.retry_after.clear()
        e.fail_chunk = None
        e.worker.run_once()
        self.assertEqual(e.calls["transcribe"], [(0.0, 60.5), (60.5, 130.0), (60.5, 130.0)])
        self.assertEqual(e.calls["analyse"], 1)
        self.assertEqual(e.store.recording(body["id"])["status"], "done")

    def test_gives_up_after_max_attempts(self):
        e = Env(self)
        _, body = e.upload()
        e.fail_chunk = 1
        for _ in range(3):
            e.worker.retry_after.clear()
            e.fail_chunk = len(e.calls["transcribe"]) + 1
            e.worker.run_once()
        rec = e.store.recording(body["id"])
        self.assertEqual((rec["status"], rec["attempts"]), ("failed", 3))
        self.assertIn("stt down", rec["error"])

    def test_approval_calls_task_sink_only_after_a_person_approves(self):
        FakeMCP.sse, FakeMCP.seen = False, []
        srv = HTTPServer(("127.0.0.1", 0), FakeMCP)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        e = Env(self, sinks=[{"name": "t", "kind": "task", "enabled": True, "tool": "create_task",
                              "mcp": {"url": f"http://127.0.0.1:{srv.server_port}/mcp"},
                              "args": {"name": "{title}", "due": "{due}"}}])
        e.settings.cfg["tasks"] = {"mode": "confirm"}
        e.upload()
        e.worker.run_once()
        self.assertEqual(FakeMCP.seen, [])                      # proposing wrote nothing
        first, second = e.store.proposals("pending")
        code, body = e.req("POST", f"/v1/proposals/{first['id']}/approve")
        self.assertEqual((code, body["result"]), (200, "approved"))
        call = [s for s in FakeMCP.seen if s[0] == "tools/call"][0][3]
        self.assertEqual(call["arguments"], {"name": "Call Sam about the keys", "due": "2026-10-16"})
        self.assertEqual(e.req("POST", f"/v1/proposals/{first['id']}/approve")[0], 409)
        self.assertEqual(e.req("POST", f"/v1/proposals/{second['id']}/reject")[1]["result"], "rejected")
        self.assertEqual(len([s for s in FakeMCP.seen if s[0] == "tools/call"]), 1)

    def test_review_page_works_by_token_and_not_across_recordings(self):
        e = Env(self)
        e.upload()
        e.worker.run_once()
        a = e.store.proposals("pending")[0]
        code, page = e.req("GET", f"/review/{a['token']}", token=None)
        self.assertEqual(code, 200)
        self.assertIn("Call Sam about the keys", page)
        self.assertEqual(e.req("GET", "/review/not-a-token", token=None)[0], 404)
        code, page = e.req("POST", f"/review/{a['token']}/{a['id']}/approve", token=None)
        self.assertEqual(code, 200)
        self.assertEqual(e.store.proposal(a["id"])["status"], "approved")

    def test_failing_task_sink_leaves_the_proposal_pending(self):
        e = Env(self, sinks=[{"name": "t", "kind": "task", "enabled": True, "tool": "x",
                              "mcp": {"url": "http://127.0.0.1:1/mcp"}}])
        e.upload()
        e.worker.run_once()
        p = e.store.proposals("pending")[0]
        self.assertEqual(e.req("POST", f"/v1/proposals/{p['id']}/approve")[0], 502)
        self.assertEqual(e.store.proposal(p["id"])["status"], "pending")

    def test_failing_note_sink_does_not_fail_the_recording(self):
        e = Env(self, sinks=[{"name": "n", "kind": "note", "enabled": True, "tool": "x",
                              "mcp": {"url": "http://127.0.0.1:1/mcp"}}])
        _, body = e.upload()
        e.worker.run_once()
        rec = e.store.recording(body["id"])
        self.assertEqual(rec["status"], "done")
        self.assertIn("n:", rec["error"])
        self.assertTrue(Path(rec["note_path"]).exists())


if __name__ == "__main__":
    unittest.main()


class DateContextTests(unittest.TestCase):
    def test_recording_date_reaches_the_model(self):
        e = Env(self)
        seen = []
        e.worker._chat = lambda base, key, model, messages, json_mode=False, **kw: seen.append(messages) or RESULT
        e.upload(**{"X-Recorded-At": "1760000000"})   # a Sunday in October 2025
        e.worker.run_once()
        prompt = seen[-1][1]["content"]
        self.assertIn("The recording was made on", prompt)
        self.assertIn("2025-10-0", prompt)
        self.assertIn("Calendar:", prompt)
        self.assertIn("(the day of the recording)", prompt)

    def test_timings_are_recorded(self):
        e = Env(self)
        _, body = e.upload()
        e.worker.run_once()
        t = e.store.progress(body["id"])["timings"]
        self.assertEqual(len(t["stt"]), 2)
        self.assertIn("summary_s", t)
        self.assertIn("analyse_s", t)


class TickerTests(unittest.TestCase):
    def test_target_detection(self):
        from novak_ingest.notify import is_ticker
        self.assertTrue(is_ticker("ticker"))
        self.assertTrue(is_ticker("notify.ticker"))
        self.assertFalse(is_ticker("mobile_app_pixel"))

    def test_ticker_call_shape_and_worker_routing(self):
        seen = []

        class HA(BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def do_POST(self):
                seen.append((self.path, self.headers["Authorization"],
                             json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers()
                self.wfile.write(b"[]")

        srv = HTTPServer(("127.0.0.1", 0), HA)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        e = Env(self)
        e.settings.ha_url = f"http://127.0.0.1:{srv.server_port}"
        e.settings.ha_target = "notify.ticker"
        e.settings.ticker_category = "novak"
        e.worker._notify = None                      # use the real notifier
        e.upload()
        e.worker.run_once()
        path, auth, body = seen[0]
        self.assertEqual((path, auth), ("/api/services/ticker/notify", "Bearer t"))
        self.assertEqual(body["category"], "novak")
        self.assertIn("2 task(s) to approve", body["title"])
        self.assertTrue(body["data"]["url"].startswith("http://spire:13409/review/"))
        self.assertEqual(body["data"]["url"], body["data"]["clickAction"])


class SinkValuesTests(unittest.TestCase):
    def test_note_sink_gets_iso_timestamp_and_list_args_render(self):
        FakeMCP.sse, FakeMCP.seen = False, []
        srv = HTTPServer(("127.0.0.1", 0), FakeMCP)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        e = Env(self, sinks=[{"name": "m", "kind": "memory", "enabled": True, "tool": "retain",
                              "mcp": {"url": f"http://127.0.0.1:{srv.server_port}/mcp"},
                              "args": {"content": "{title}", "document_id": "recording-{recording_id}",
                                       "timestamp": "{recorded_iso}", "tags": ["ingest"]}}])
        _, body = e.upload()
        e.worker.run_once()
        call = [s for s in FakeMCP.seen if s[0] == "tools/call"][0][3]["arguments"]
        self.assertEqual(call["document_id"], f"recording-{body['id']}")
        self.assertRegex(call["timestamp"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
        self.assertEqual(call["tags"], ["ingest"])


class AutoTaskTests(unittest.TestCase):
    def sink(self, test):
        FakeMCP.sse, FakeMCP.seen = False, []
        srv = HTTPServer(("127.0.0.1", 0), FakeMCP)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        test.addCleanup(srv.shutdown)
        return {"name": "t", "kind": "task", "enabled": True, "tool": "create_task",
                "mcp": {"url": f"http://127.0.0.1:{srv.server_port}/mcp"}, "args": {"name": "{title}"}}

    def test_auto_mode_adds_tasks_without_asking_and_says_so(self):
        e = Env(self, sinks=[self.sink(self)])
        e.upload()
        e.worker.run_once()
        calls = [s[3]["arguments"]["name"] for s in FakeMCP.seen if s[0] == "tools/call"]
        self.assertEqual(calls, ["Call Sam about the keys", "Cancel the internet"])
        self.assertEqual(e.store.proposals("pending"), [])
        self.assertIn("2 task(s) added", e.calls["notify"][0][3])

    def test_confirm_mode_still_waits(self):
        e = Env(self, sinks=[self.sink(self)])
        e.settings.cfg["tasks"]["mode"] = "confirm"
        e.upload()
        e.worker.run_once()
        self.assertEqual([s for s in FakeMCP.seen if s[0] == "tools/call"], [])
        self.assertEqual(len(e.store.proposals("pending")), 2)
        self.assertIn("task(s) to approve", e.calls["notify"][0][3])

    def test_no_task_sink_means_tasks_wait_even_in_auto(self):
        e = Env(self)
        e.upload()
        e.worker.run_once()
        self.assertEqual(len(e.store.proposals("pending")), 2)

    def test_a_failing_sink_leaves_that_task_pending(self):
        sink = {"name": "t", "kind": "task", "enabled": True, "tool": "x", "mcp": {"url": "http://127.0.0.1:1/mcp"}}
        e = Env(self, sinks=[sink])
        e.upload()
        e.worker.run_once()
        self.assertEqual(len(e.store.proposals("pending")), 2)
        self.assertIn("task(s) to approve", e.calls["notify"][0][3])


class FakeGateway(BaseHTTPRequestHandler):
    """Namespaced tools per person, like the real gateway; records who called what."""
    accounts = {"tmeuze": ["tududi_1_tmeuze__create_task", "hindsight_1_tmeuze__retain"],
                "ushy": ["tududi_1_ushy__create_task"]}
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        who = self.headers.get("X-Novak-User")
        type(self).seen.append((msg.get("method"), self.headers.get("Authorization"), who, msg.get("params")))
        if "id" not in msg:
            self.send_response(202); self.send_header("Content-Length", "0"); self.end_headers(); return
        m = msg["method"]
        if m == "initialize":
            res = {"protocolVersion": "2025-03-26", "capabilities": {}}
        elif m == "tools/list":
            res = {"tools": [{"name": n} for n in type(self).accounts.get(who, [])]}
        else:
            res = {"content": [{"type": "text", "text": "ok"}]}
        body = json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class GatewaySinkTests(unittest.TestCase):
    def env(self, sinks, **owners):
        FakeGateway.seen = []
        srv = HTTPServer(("127.0.0.1", 0), FakeGateway)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        e = Env(self, sinks=sinks)
        e.settings.gateway_url = f"http://127.0.0.1:{srv.server_port}/mcp"
        e.settings.gateway_key = "ingest-key"
        e.settings.cfg["owners"] = {"default": "", "sources": {}, "people": {}, **owners}
        return e

    def calls(self):
        return [(s[2], s[3]["name"], s[3]["arguments"]) for s in FakeGateway.seen if s[0] == "tools/call"]

    TASK = {"name": "t", "kind": "task", "enabled": True, "service": "tududi", "tool": "create_task",
            "args": {"name": "{title}"}}
    MEM = {"name": "m", "kind": "memory", "enabled": True, "service": "hindsight", "tool": "retain",
           "args": {"content": "{title}", "tags": ["{who}"]}}

    def test_acts_as_the_owner_with_the_trusted_key(self):
        e = self.env([self.TASK], default="tmeuze")
        e.upload()
        e.worker.run_once()
        self.assertEqual([c[:2] for c in self.calls()], [("tmeuze", "tududi_1_tmeuze__create_task")] * 2)
        self.assertTrue(all(s[1] == "Bearer ingest-key" for s in FakeGateway.seen))
        self.assertEqual(e.store.recordings()[0]["owner"], "tmeuze")

    def test_source_label_and_owner_header_pick_the_person(self):
        e = self.env([self.TASK], sources={"ushy-pendant": "ushy"}, default="tmeuze")
        e.upload(**{"X-Source": "ushy-pendant"})
        e.upload(b"other", **{"X-Owner": "tmeuze"})
        owners = sorted(r["owner"] for r in e.store.recordings())
        self.assertEqual(owners, ["tmeuze", "ushy"])
        while e.worker.run_once():
            pass
        self.assertEqual({c[0] for c in self.calls()}, {"tmeuze", "ushy"})

    def test_owner_without_the_service_is_reported_not_guessed(self):
        e = self.env([self.TASK, self.MEM], default="ushy")
        e.upload()
        e.worker.run_once()
        # ushy has Tududi but no Hindsight: tasks go through, the memory sink reports instead of guessing
        self.assertEqual({c[1] for c in self.calls()}, {"tududi_1_ushy__create_task"})

    def test_per_person_vars_fill_arguments(self):
        mem = dict(self.MEM, args={"content": "{title}", "tags": ["{bank_tag}"]})
        e = self.env([mem], default="tmeuze",
                     people={"tmeuze": {"vars": {"bank_tag": "mine"}}})
        e.upload()
        e.worker.run_once()
        self.assertEqual(self.calls()[0][2]["tags"], ["mine"])

    def test_no_owner_or_no_key_does_not_call_anything(self):
        e = self.env([self.TASK])                                # no default owner
        e.upload()
        e.worker.run_once()
        self.assertEqual(self.calls(), [])
        self.assertEqual(len(e.store.proposals("pending")), 2)
        e2 = self.env([self.TASK], default="tmeuze")
        e2.settings.gateway_key = ""
        e2.upload()
        e2.worker.run_once()
        self.assertEqual(self.calls(), [])

    def test_approval_acts_as_the_recordings_owner(self):
        e = self.env([self.TASK], default="ushy")
        e.settings.cfg["tasks"] = {"mode": "confirm"}      # not in place: DEFAULTS is shared
        e.upload()
        e.worker.run_once()
        first = e.store.proposals("pending")[0]
        e.req("POST", f"/v1/proposals/{first['id']}/approve")
        self.assertEqual([c[:2] for c in self.calls()], [("ushy", "tududi_1_ushy__create_task")])


class FakeApprise(BaseHTTPRequestHandler):
    """Records what Novak posts; `code` lets a test make Apprise refuse."""
    seen = []
    code = 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        from urllib.parse import parse_qs
        body = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        type(self).seen.append((self.path, self.headers.get("Content-Type"), {k: v[0] for k, v in body.items()}))
        self.send_response(type(self).code)
        self.send_header("Content-Length", "0")
        self.end_headers()


class AppriseNoticeTests(unittest.TestCase):
    TASK = {"name": "t", "kind": "task", "enabled": True, "service": "tududi", "tool": "create_task", "args": {"name": "{title}"}}

    def env(self, **kw):
        FakeApprise.seen, FakeApprise.code = [], kw.pop("code", 200)
        srv = HTTPServer(("127.0.0.1", 0), FakeApprise)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        gw = HTTPServer(("127.0.0.1", 0), FakeGateway)
        FakeGateway.seen = []
        threading.Thread(target=gw.serve_forever, daemon=True).start()
        self.addCleanup(gw.shutdown)
        e = Env(self, sinks=[self.TASK])
        e.settings.gateway_url, e.settings.gateway_key = f"http://127.0.0.1:{gw.server_port}/mcp", "k"
        e.settings.apprise_url, e.settings.apprise_key = f"http://127.0.0.1:{srv.server_port}", "novak-key/with space"
        e.settings.cfg["owners"] = {"default": "tmeuze", "sources": {}, "people": {"tmeuze": {"notice_tag": "novak-tmeuze"}}}
        e.settings.cfg["notices"] = {"admin_tag": "novak-admin"}
        for k, v in kw.items():
            setattr(e.settings, k, v)
        return e

    def test_tasks_added_automatically_are_a_plain_notice_to_the_persons_own_tag(self):
        e = self.env()
        e.upload()
        e.worker.run_once()
        self.assertEqual(len(FakeApprise.seen), 1)
        path, ctype, form = FakeApprise.seen[0]
        self.assertEqual(path, "/notify/novak-key%2Fwith%20space")                  # key is URL-quoted, never in the body
        self.assertEqual(ctype, "application/x-www-form-urlencoded")
        self.assertEqual((form["tag"], form["type"]), ("novak-tmeuze", "success"))
        self.assertIn("task(s) added", form["title"])
        self.assertEqual(e.calls["notify"], [])                                      # and nothing went to Home Assistant

    def test_a_task_waiting_for_approval_still_goes_to_home_assistant(self):
        e = self.env()
        e.settings.cfg["tasks"] = {"mode": "confirm"}
        e.upload()
        e.worker.run_once()
        self.assertEqual(FakeApprise.seen, [])
        self.assertEqual(len(e.calls["notify"]), 1)                                   # buttons need Home Assistant

    def test_a_refusing_or_unreachable_apprise_falls_back_to_home_assistant(self):
        e = self.env(code=403)
        e.upload()
        e.worker.run_once()
        self.assertEqual(len(FakeApprise.seen), 1)
        self.assertEqual(len(e.calls["notify"]), 1)                                   # the notice is not lost
        e2 = self.env()
        e2.settings.apprise_url = "http://127.0.0.1:1"
        e2.upload()
        e2.worker.run_once()
        self.assertEqual(len(e2.calls["notify"]), 1)

    def test_a_person_with_no_tag_or_no_apprise_uses_home_assistant_as_before(self):
        e = self.env()
        e.settings.cfg["owners"]["people"] = {}
        e.upload()
        e.worker.run_once()
        self.assertEqual((FakeApprise.seen, len(e.calls["notify"])), ([], 1))
        e = self.env(apprise_key="")
        e.upload()
        e.worker.run_once()
        self.assertEqual((FakeApprise.seen, len(e.calls["notify"])), ([], 1))

    def test_a_recording_that_gives_up_tells_the_admin_tag(self):
        e = self.env()
        e.fail_chunk = 1
        e.settings.cfg["max_attempts"] = 1
        e.upload()
        e.worker.run_once()
        self.assertEqual(e.store.recordings()[0]["status"], "failed")
        tags = [f["tag"] for _, _, f in FakeApprise.seen]
        self.assertEqual(tags, ["novak-admin"])
        self.assertEqual(FakeApprise.seen[0][2]["type"], "failure")

    def test_the_sender_rejects_a_bad_type_and_reports_without_the_key(self):
        from novak_ingest import notify
        with self.assertRaises(ValueError):
            notify.apprise_notify("http://x", "k", "t", "T", "b", "shout")
        FakeApprise.seen, FakeApprise.code = [], 500
        srv = HTTPServer(("127.0.0.1", 0), FakeApprise)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        with self.assertRaises(RuntimeError) as cm:
            notify.apprise_notify(f"http://127.0.0.1:{srv.server_port}", "secret-key-123", "t", "T", "b")
        self.assertNotIn("secret-key-123", str(cm.exception))
        self.assertIn("500", str(cm.exception))

    def test_a_tag_with_a_space_or_comma_is_refused_at_load(self):
        from novak_ingest.config import ConfigError, validate, DEFAULTS, _merge
        import copy
        bad = _merge(copy.deepcopy(DEFAULTS), {"owners": {"people": {"tmeuze": {"notice_tag": "a b"}}}})
        with self.assertRaises(ConfigError):
            validate(bad)
