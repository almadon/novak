import fnmatch
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "gateway"))
from novak_gateway import directory  # noqa: E402
from novak_gateway.service import SEP  # noqa: E402


def match(globs, name):
    return any(fnmatch.fnmatchcase(name, g.strip()) for g in globs.split(","))


class CodeMemoryTests(unittest.TestCase):
    """The Code preset may run on a hosted model: it must reach the code bank and never the personal one."""

    def setUp(self):
        owui = yaml.safe_load((ROOT / "registry/openwebui.yaml").read_text())["openwebui"]
        self.servers = {t["id"]: t for t in owui["tool_servers"]}
        self.models = {m["id"]: m for m in owui["models"]}
        self.gateway = yaml.safe_load((ROOT / "registry/gateway.yaml").read_text())["gateway"]
        self.code_alias = "code-memory-tmeuze".replace("-", "_")
        self.personal_alias = "hindsight-tmeuze".replace("-", "_")

    def test_the_code_preset_gets_only_the_code_connection(self):
        self.assertEqual(self.models["code"]["tools"], ["novak-code"])
        h = self.servers["novak-code"]["headers"]
        self.assertTrue(match(h["X-Novak-Scope"], "code-memory-tmeuze"))
        self.assertFalse(match(h["X-Novak-Scope"], "hindsight-tmeuze"))
        self.assertTrue(match(h["X-Novak-Tools"], f"{self.code_alias}{SEP}recall"))
        self.assertTrue(match(h["X-Novak-Tools"], f"{self.code_alias}{SEP}retain"))
        self.assertFalse(match(h["X-Novak-Tools"], f"{self.personal_alias}{SEP}recall"))
        self.assertFalse(match(h["X-Novak-Tools"], f"tududi_1_tmeuze{SEP}list_tasks"))

    def test_the_personal_presets_do_not_pick_up_the_code_bank(self):
        tools = self.servers["novak-gateway"]["headers"]["X-Novak-Tools"]
        self.assertFalse(match(tools, f"{self.code_alias}{SEP}recall"))
        self.assertTrue(match(tools, f"{self.personal_alias}{SEP}recall"))
        for m in ("novak", "novak-deep", "home"):
            self.assertNotIn("novak-code", self.models[m].get("tools", []))

    def test_the_code_bank_gets_the_same_trimmed_tool_list_as_the_personal_ones(self):
        allowed = lambda e, t: directory.tool_allowed(self.gateway["tool_filters"], e, t)
        for tool in ("recall", "retain"):
            self.assertTrue(allowed("code-memory-tmeuze", tool))
        self.assertFalse(allowed("code-memory-tmeuze", "delete_bank"))

    def test_the_prompt_forbids_personal_content(self):
        text = (ROOT / "prompts/novak-code.md").read_text()
        self.assertIn("Never retain anything personal", text)
        self.assertIn("hosted model", text)


if __name__ == "__main__":
    unittest.main()
