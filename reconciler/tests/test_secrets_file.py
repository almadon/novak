import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


class SecretsFileTests(unittest.TestCase):
    """secrets.sh on Linux: secrets live in secrets.env, never in .env (decision #69)."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        self.env = self.dir / ".env"
        self.sf = self.dir / "secrets.env"
        self.env.write_text("# config\nHOST_NAME=spire\nOLLAMA_PORT=11434\nROUTER_API_KEY=set-in-keychain\n"
                            "HINDSIGHT_API_KEY=legacy-real-value\nSOMETHING_NEW_TOKEN=pasted-by-hand\n"
                            "OWUI_ENABLE_API_KEYS=true\n")
        self.env.chmod(0o644)

    def sh(self, script):
        full = ('set -e\nENV_FILE="%s"\nSECRET_VARS=(ROUTER_API_KEY HINDSIGHT_API_KEY OMLX_API_KEY)\n'
                'source "%s"\n%s' % (self.env, REPO / "scripts" / "lib" / "secrets.sh", script))
        r = subprocess.run(["bash", "-c", full], capture_output=True, text=True,
                           env={**os.environ, "NOVAK_SECRETS_PLATFORM": "Linux", "PATH": os.environ["PATH"]})
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def test_a_new_secret_goes_to_a_private_file_and_not_into_env(self):
        self.sh('secret_set OMLX_API_KEY "abc123"')
        self.assertEqual(stat.S_IMODE(self.sf.stat().st_mode), 0o600)
        self.assertIn("OMLX_API_KEY=abc123", self.sf.read_text())
        self.assertNotIn("abc123", self.env.read_text())
        self.assertEqual(self.sh('secret_get OMLX_API_KEY').strip(), "abc123")

    def test_a_secret_not_yet_migrated_is_still_read_from_env(self):
        self.assertEqual(self.sh("secret_get HINDSIGHT_API_KEY").strip(), "legacy-real-value")

    def test_setting_a_secret_moves_it_out_of_env(self):
        self.sh('secret_set HINDSIGHT_API_KEY "fresh"')
        self.assertNotIn("HINDSIGHT_API_KEY", self.env.read_text())
        self.assertEqual(self.sh("secret_get HINDSIGHT_API_KEY").strip(), "fresh")
        self.assertEqual(self.sh('secret_set HINDSIGHT_API_KEY "fresher"; secret_get HINDSIGHT_API_KEY').strip(), "fresher")
        self.assertEqual(self.sf.read_text().count("HINDSIGHT_API_KEY="), 1)

    def test_awkward_values_round_trip(self):
        for value in ("a=b=c", "with space", r"back\slash\n", "$HOME and `tick`", 'quote"s'):
            self.sh('secret_set OMLX_API_KEY "$1"'.replace("$1", value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")))
            self.assertEqual(self.sh("secret_get OMLX_API_KEY").rstrip("\n"), value)

    def test_delete_removes_it_from_both(self):
        self.sh('secret_set OMLX_API_KEY x; secret_delete OMLX_API_KEY; secret_delete HINDSIGHT_API_KEY')
        self.assertEqual(self.sh("secret_get OMLX_API_KEY").strip(), "")
        self.assertEqual(self.sh("secret_get HINDSIGHT_API_KEY").strip(), "")
        self.assertNotIn("HINDSIGHT_API_KEY", self.env.read_text())

    def test_migration_moves_real_values_drops_placeholders_and_leaves_config_alone(self):
        out = self.sh("secrets_migrate")
        self.assertIn("moved HINDSIGHT_API_KEY", out)
        self.assertIn("moved SOMETHING_NEW_TOKEN", out)                     # named like a secret, so moved
        self.assertIn("dropped ROUTER_API_KEY", out)
        self.assertNotIn("legacy-real-value", out)                           # names only, never values
        env = self.env.read_text()
        self.assertEqual(env, "# config\nHOST_NAME=spire\nOLLAMA_PORT=11434\nOWUI_ENABLE_API_KEYS=true\n")
        self.assertIn("HINDSIGHT_API_KEY=legacy-real-value", self.sf.read_text())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o644)       # .env's own mode untouched
        self.assertEqual(self.sh("secrets_migrate").strip(), "")             # idempotent

    def test_the_permission_check_names_each_problem(self):
        self.assertIn("missing", self.sh("secret_permcheck"))
        self.sh('secret_set OMLX_API_KEY x')
        self.assertIn("still in", self.sh("secret_permcheck"))               # HINDSIGHT_API_KEY etc. remain in .env
        self.sh("secrets_migrate")
        self.assertEqual(self.sh("secret_permcheck").strip(), "ok")
        self.sf.chmod(0o644)
        self.assertIn("loose", self.sh("secret_permcheck"))

    def test_a_secret_already_in_the_secrets_file_wins_over_a_stale_env_line(self):
        self.sf.write_text("HINDSIGHT_API_KEY=current\n")
        self.sf.chmod(0o600)
        self.assertEqual(self.sh("secret_get HINDSIGHT_API_KEY").strip(), "current")
        self.assertIn("dropped HINDSIGHT_API_KEY (secrets.env already had it)", self.sh("secrets_migrate"))
        self.assertEqual(self.sh("secret_get HINDSIGHT_API_KEY").strip(), "current")


if __name__ == "__main__":
    unittest.main()
