import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "reconciler"))
import pi_config  # noqa: E402


class PiConfigTests(unittest.TestCase):
    def test_the_provider_points_at_the_router_and_names_the_code_and_chat_roles(self):
        cfg = pi_config.build("http://100.125.10.15:13402/v1/")
        p = cfg["providers"]["novak"]
        self.assertEqual((p["baseUrl"], p["api"]), ("http://100.125.10.15:13402/v1", "openai-completions"))
        self.assertEqual([m["id"] for m in p["models"]], ["code", "chat", "deep"])

    def test_the_key_is_an_environment_reference_never_a_value(self):
        text = json.dumps(pi_config.build("http://x/v1"))
        self.assertIn('"$ROUTER_API_KEY"', text)
        for forbidden in ("sk-", "Bearer"):
            self.assertNotIn(forbidden, text)

    def test_the_declared_window_and_address_come_from_the_deployment(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pi_config.main([], env={"OLLAMA_CONTEXT_LENGTH": "8192", "ROUTER_BIND": "100.1.2.3", "ROUTER_PORT": "13402"})
        cfg = json.loads(buf.getvalue())
        self.assertTrue(all(m["contextWindow"] == 8192 for m in cfg["providers"]["novak"]["models"]))
        self.assertEqual(cfg["providers"]["novak"]["baseUrl"], "http://100.1.2.3:13402/v1")

    def test_the_editing_rules_say_the_two_things_that_fixed_the_loop(self):
        text = (REPO / "prompts" / "novak-pi.md").read_text().partition("\n---\n")[2]
        self.assertIn("exactly ONE place", text)
        self.assertIn("sed", text)


if __name__ == "__main__":
    unittest.main()
