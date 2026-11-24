import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "reconciler"))
import bench  # noqa: E402
import warm  # noqa: E402

ENGINES = [{"name": "ollama-local", "models": [
    {"role": "chat", "model": "qwen3:14b"}, {"role": "ha-voice", "model": "qwen3:4b-ctx8k"},
    {"role": "task", "model": "qwen3:4b-ctx8k"}, {"role": "code", "model": "coder:14b"}]}]


class FakeOllama(BaseHTTPRequestHandler):
    loaded, generated, fail = [], [], set()

    def log_message(self, *a):
        pass

    def reply(self, code, body):
        raw = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        self.reply(200, {"models": [{"name": n} for n in type(self).loaded]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).generated.append(body)
        if body["model"] in type(self).fail:
            return self.reply(404, {"error": "model not found"})
        self.reply(200, {"done": True})


class WarmTests(unittest.TestCase):
    def serve(self, loaded=(), fail=()):
        FakeOllama.loaded, FakeOllama.generated, FakeOllama.fail = list(loaded), [], set(fail)
        srv = HTTPServer(("127.0.0.1", 0), FakeOllama)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}"

    def test_the_voice_and_chat_models_of_an_ollama_engine_are_chosen_once_each(self):
        self.assertEqual(warm.models_to_warm({}, ENGINES), ["qwen3:4b-ctx8k", "qwen3:14b"])

    def test_other_engines_are_not_warmed(self):
        self.assertEqual(warm.models_to_warm({}, [{"name": "omlx", "models": ENGINES[0]["models"]}]), [])

    def test_the_setting_overrides_the_engine_and_empty_turns_it_off(self):
        self.assertEqual(warm.models_to_warm({"OLLAMA_WARM_MODELS": "a:1, b:2 a:1"}, ENGINES), ["a:1", "b:2"])
        self.assertEqual(warm.models_to_warm({"OLLAMA_WARM_MODELS": ""}, ENGINES), [])

    def test_a_cold_model_is_loaded_with_an_empty_prompt_and_a_loaded_one_is_skipped(self):
        url = self.serve(loaded=["qwen3:4b-ctx8k"])
        lines = []
        self.assertEqual(warm.warm(url, ["qwen3:4b-ctx8k", "qwen3:14b"], lines.append), 0)
        self.assertEqual(FakeOllama.generated, [{"model": "qwen3:14b", "prompt": ""}])
        self.assertIn("already loaded", lines[0])
        self.assertIn("loaded in", lines[1])

    def test_a_model_that_will_not_load_fails_the_run_but_not_the_others(self):
        url = self.serve(fail=["bad:1"])
        lines = []
        self.assertEqual(warm.warm(url, ["bad:1", "good:1"], lines.append), 1)
        self.assertTrue(any("FAILED" in l for l in lines))
        self.assertEqual([g["model"] for g in FakeOllama.generated], ["bad:1", "good:1"])

    def test_an_unreachable_server_is_an_error_not_a_crash(self):
        lines = []
        self.assertEqual(warm.warm("http://127.0.0.1:1", ["x:1"], lines.append), 1)
        self.assertIn("cannot reach", lines[0])

    def test_write_makes_the_file_the_boot_container_reads(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(home, ignore_errors=True))
        warm.main(["--write"], env={"NOVAK_HOME": str(home), "OLLAMA_WARM_MODELS": "a:1 b:2"})
        self.assertEqual((home / "warm-models.txt").read_text(), "a:1\nb:2\n")
        warm.main(["--write"], env={"NOVAK_HOME": str(home), "OLLAMA_WARM_MODELS": ""})
        self.assertEqual((home / "warm-models.txt").read_text(), "")             # always exists, so the mount never makes a folder

    def test_the_address_follows_the_bind_setting(self):
        self.assertEqual(warm.base_url({"OLLAMA_BIND": "100.1.2.3", "OLLAMA_PORT": "9"}), "http://100.1.2.3:9")
        self.assertEqual(warm.base_url({"OLLAMA_BIND": "0.0.0.0"}), "http://127.0.0.1:11434")


class FakeRouter(BaseHTTPRequestHandler):
    seen, status = [], 200

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append((self.headers.get("Authorization"), body))
        if type(self).status != 200:
            self.send_response(type(self).status); self.end_headers(); return
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for t in ("Hello", " there", "."):
            self.wfile.write(("data: " + json.dumps({"choices": [{"delta": {"content": t}}]}) + "\n\n").encode())
        self.wfile.write(("data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 2100, "completion_tokens": 3}}) + "\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")


class QuietSampler(bench.Sampler):
    def run(self):
        pass


class BenchTests(unittest.TestCase):
    def serve(self, status=200):
        FakeRouter.seen, FakeRouter.status = [], status
        srv = HTTPServer(("127.0.0.1", 0), FakeRouter)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        return f"http://127.0.0.1:{srv.server_port}/v1"

    def run_bench(self, url, *args, env=None):
        lines = []
        code = bench.main(["--url", url, *args], env=env if env is not None else {"ROUTER_API_KEY": "k"},
                          out=lines.append, sampler=QuietSampler)
        return code, lines

    def test_each_role_and_size_is_one_line_with_first_token_and_speed(self):
        code, lines = self.run_bench(self.serve(), "--roles", "chat,task", "--sizes", "0,1")
        self.assertEqual(code, 0)
        rows = [l for l in lines if "first token" in l]
        self.assertEqual(len(rows), 4)
        self.assertIn("chat +0", rows[0])
        self.assertIn("prompt  2100", rows[0])
        self.assertEqual([b["model"] for _, b in FakeRouter.seen], ["chat", "chat", "task", "task"])

    def test_the_request_is_streamed_with_the_key_and_a_bigger_size_sends_a_bigger_prompt(self):
        self.run_bench(self.serve(), "--roles", "chat", "--sizes", "0,2")
        auth, small = FakeRouter.seen[0]
        _, big = FakeRouter.seen[1]
        self.assertEqual(auth, "Bearer k")
        self.assertTrue(small["stream"])
        self.assertGreater(len(big["messages"][0]["content"]), len(small["messages"][0]["content"]) + 5000)

    def test_a_failing_router_is_reported_and_the_exit_code_says_so(self):
        code, lines = self.run_bench(self.serve(status=500), "--roles", "chat", "--sizes", "0")
        self.assertEqual(code, 1)
        self.assertTrue(any("ERROR" in l for l in lines))

    def test_no_key_stops_with_a_clear_message(self):
        self.assertEqual(self.run_bench("http://127.0.0.1:1/v1", env={})[0], 2)

    def test_the_gpu_columns_only_appear_when_there_is_a_gpu_to_read(self):
        row = bench.line("x", {"prompt": 1, "ttft": 1.0, "tokens": 5, "rate": 5.0, "total": 2.0,
                               "gpu": None, "gpu_max": None, "cpu": None, "vram": None})
        self.assertNotIn("gpu", row)
        row = bench.line("x", {"prompt": 1, "ttft": 1.0, "tokens": 5, "rate": 5.0, "total": 2.0,
                               "gpu": 80.0, "gpu_max": 99.0, "cpu": 20.0, "vram": 10.0})
        self.assertIn("gpu  80%", row)


if __name__ == "__main__":
    unittest.main()
