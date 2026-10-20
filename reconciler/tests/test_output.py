import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ESC = "\x1b["


def run_reconcile(env_extra=None):
    home = Path(tempfile.mkdtemp())
    (home / "registry").mkdir()
    (home / "registry" / "mcp-servers.yaml").write_text((REPO / "registry" / "mcp-servers.yaml").read_text())
    (home / ".env").write_text("HOST_NAME=spire\n")
    env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
    env.update({"NOVAK_HOME": str(home), **(env_extra or {})})
    r = subprocess.run([sys.executable, str(REPO / "reconciler" / "reconcile.py"), "--dry-run"],
                       capture_output=True, text=True, env=env)
    return r.stdout + r.stderr


class ReconcilerOutputTests(unittest.TestCase):
    def test_piped_output_is_the_plain_format_other_tools_parse(self):
        out = run_reconcile()
        self.assertNotIn(ESC, out)
        self.assertNotIn("━", out)
        self.assertRegex(out, r"(?m)^external: outline-everything -> https://\S+  \[token: OUTLINE_EVERYTHING_API_KEY\]$")
        self.assertRegex(out, r"(?m)^  ! hindsight-tmeuze: elevated — accepted by tmeuze on 2026-08-19$")
        # the same parsing `novak registry --check` does
        m = re.search(r"^external: ([a-z0-9-]+) -> ([^ ]+).*\[token: ([A-Z_]+)\]", out, re.M)
        self.assertEqual((m.group(1), m.group(3)), ("outline-everything", "OUTLINE_EVERYTHING_API_KEY"))

    def test_forced_colour_gives_sections_emoji_and_colour(self):
        out = run_reconcile({"FORCE_COLOR": "1"})
        plain = re.sub(r"\x1b\[[0-9;]*m", "", out)
        self.assertIn(ESC, out)
        self.assertIn("🔌  MCP servers", plain)
        self.assertIn("⚠️   Accepted risk", plain)
        self.assertRegex(plain, r"⚠️\s+elevated\s+hindsight-tmeuze\s+accepted by tmeuze on 2026-08-19")
        self.assertIn("↳ Personal memories", plain)           # reasons indented under their entry
        self.assertIn("🔗 external", plain)

    def test_no_colour_wins_over_force_colour(self):
        out = run_reconcile({"FORCE_COLOR": "1", "NO_COLOR": "1"})
        self.assertNotIn(ESC, out)
        self.assertNotIn("━", out)

    def test_dangerous_risk_gets_its_own_icon(self):
        import yaml
        home = Path(tempfile.mkdtemp())
        (home / "registry").mkdir()
        reg = yaml.safe_load((REPO / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"].append({
            "name": "risky", "kind": "external", "url": "http://x:1/mcp", "enabled": True,
            "risk": {"level": "dangerous", "why": ["can run code"], "accepted_by": "me", "accepted_on": "2026-01-01"}})
        (home / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        (home / ".env").write_text("HOST_NAME=spire\n")
        r = subprocess.run([sys.executable, str(REPO / "reconciler" / "reconcile.py"), "--dry-run"], capture_output=True,
                           text=True, env={**os.environ, "NOVAK_HOME": str(home), "FORCE_COLOR": "1"})
        self.assertIn("🚨", r.stdout)


class ShellHelperTests(unittest.TestCase):
    def sh(self, snippet, env=None):
        e = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
        e.update(env or {})
        return subprocess.run(["bash", "-c", f"source {REPO}/scripts/lib/ui.sh; {snippet}"],
                              capture_output=True, text=True, env=e)

    def test_section_ok_warn_and_skip_render_with_emoji(self):
        r = self.sh('ui_section "🔐" "Secrets"; ui_ok "17 loaded"; ui_warn "careful"; ui_skip console "not configured: X"',
                    {"FORCE_COLOR": "1"})
        out = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)
        self.assertIn("━━ 🔐  Secrets ━", out)
        self.assertIn("✅ 17 loaded", out)
        self.assertIn("⚠️  careful", out)
        self.assertIn("⏭️  console not configured: X", out)
        self.assertIn(ESC, r.stdout + r.stderr)

    def test_no_colour_output_has_no_escapes_but_keeps_the_words(self):
        r = self.sh('ui_section "🧩" "Optional services"; ui_ok "on: router"', {"NO_COLOR": "1", "FORCE_COLOR": "1"})
        self.assertNotIn(ESC, r.stdout)
        self.assertIn("Optional services", r.stdout)

    def test_skip_later_collects_for_one_summary(self):
        r = self.sh('ui_skip_later a "why a"; ui_skip_later b "why b"; '
                    'for i in "${!ui_skipped_names[@]}"; do echo "${ui_skipped_names[$i]}=${ui_skipped_why[$i]}"; done')
        self.assertEqual(r.stdout.split("\n")[:2], ["a=why a", "b=why b"])

    def test_up_sh_parses(self):
        for f in ("scripts/up.sh", "scripts/lib/ui.sh", "scripts/novak"):
            self.assertEqual(subprocess.run(["bash", "-n", str(REPO / f)]).returncode, 0, f)


if __name__ == "__main__":
    unittest.main()


class UrlEnvReconcileTests(unittest.TestCase):
    def entry_registry(self, env_text):
        import yaml
        home = Path(tempfile.mkdtemp())
        (home / "registry").mkdir()
        reg = yaml.safe_load((REPO / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"].append({"name": "secret-addr", "kind": "external", "url_env": "SECRET_ADDR_URL", "enabled": True})
        (home / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        (home / ".env").write_text(env_text)
        return home

    def run_reconcile_at(self, home):
        r = subprocess.run([sys.executable, str(REPO / "reconciler" / "reconcile.py"), "--dry-run"], capture_output=True,
                           text=True, env={**{k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}, "NOVAK_HOME": str(home)})
        return r.stdout + r.stderr

    def test_unset_variable_means_skipped_with_the_reason_and_set_means_listed_without_the_value(self):
        out = self.run_reconcile_at(self.entry_registry("HOST_NAME=spire\n"))
        self.assertIn("skipped:  secret-addr — url variable SECRET_ADDR_URL is not set", out)
        out = self.run_reconcile_at(self.entry_registry("HOST_NAME=spire\nSECRET_ADDR_URL=http://10.0.0.1:9/private_abc123\n"))
        self.assertIn("external: secret-addr -> env:SECRET_ADDR_URL", out)
        self.assertNotIn("private_abc123", out)

    def test_exactly_one_of_url_and_url_env(self):
        import yaml
        home = Path(tempfile.mkdtemp())
        (home / "registry").mkdir()
        reg = yaml.safe_load((REPO / "registry" / "mcp-servers.yaml").read_text())
        reg["servers"].append({"name": "both", "kind": "external", "url": "http://x:1/", "url_env": "X_URL", "enabled": True})
        (home / "registry" / "mcp-servers.yaml").write_text(yaml.safe_dump(reg))
        (home / ".env").write_text("HOST_NAME=spire\n")
        self.assertIn("exactly one of url or url_env", self.run_reconcile_at(home))
