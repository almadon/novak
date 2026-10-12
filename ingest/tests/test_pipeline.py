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
from http.server import HTTPServer

RESULT = json.dumps({
    "title": "Plan the move", "summary": "They discussed moving house.",
    "key_points": ["Movers booked"], "decisions": ["Move on the 3rd"], "people": ["Sam"],
    "tasks": [{"title": "Call Sam about the keys", "detail": "before Friday", "due": "2026-10-16"},
              {"title": "Cancel the internet", "detail": "", "due": None}]})


class Env:
    def __init__(self, test, sinks=None, busy=False):
        self.dir = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        cfg = _merge(DEFAULTS, {"sinks": sinks or []})
        self.settings = Settings(
            data=self.dir, token="secret", public_url="http://spire:13409", stt_url="http://stt",
            llm_base_url="http://router", llm_api_key="none", ollama_url="http://ollama",
            keep_alive_s=86400, ha_url="http://ha", ha_token="t", ha_target="mobile_app_x",
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
