import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
IGNORE = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".venv", "*.pyc", ".env")


def git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True,
                          env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}).stdout


class Deployment:
    """A checkout cloned from a bare 'remote', a NOVAK_HOME, and a stub docker."""

    def __init__(self, test):
        self.root = Path(tempfile.mkdtemp())
        test.addCleanup(lambda: shutil.rmtree(self.root, ignore_errors=True))
        seed = self.root / "seed"
        shutil.copytree(REPO, seed, ignore=IGNORE)
        git(seed, "init", "-q", "-b", "main")
        git(seed, "add", "-A")
        git(seed, "commit", "-q", "-m", "seed")
        self.remote = self.root / "remote.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(self.remote)], check=True)
        self.checkout = self.root / "checkout"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.checkout)], check=True)
        self.seed = seed
        git(seed, "remote", "add", "origin", str(self.remote))
        self.home = self.root / "home"
        (self.home / "registry").mkdir(parents=True)
        env = (REPO / ".env.example").read_text().replace("set-in-keychain", "testvalue").replace("HOST_NAME=EDIT-ME", "HOST_NAME=spire")
        (self.home / ".env").write_text(env)
        (self.home / ".venv" / "bin").mkdir(parents=True)
        for name in ("python3", "python"):                      # wrappers: a bare symlink would lose this interpreter's packages
            py = self.home / ".venv" / "bin" / name
            py.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n')
            py.chmod(0o755)
        shim = self.root / "shim"
        shim.mkdir()
        d = shim / "docker"
        d.write_text("#!/usr/bin/env bash\ncase \"$*\" in\n  *\" pull\"*) echo STUB-PULL ;;\n"
                     "  *\" ps \"*) printf 'SERVICE\\tSTATUS\\tPORTS\\n' ;;\nesac\nexit 0\n")
        d.chmod(0o755)
        self.shim = shim

    def push_new_commit(self):
        (self.seed / "NEWFILE.txt").write_text("hello")
        git(self.seed, "add", "-A")
        git(self.seed, "commit", "-q", "-m", "a new upstream commit")
        git(self.seed, "push", "-q", "origin", "main")

    def update(self, *args):
        env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR")}
        env.update({"PATH": f"{self.shim}:{os.environ['PATH']}", "NOVAK_HOME": str(self.home),
                    "NOVAK_SECRETS_PLATFORM": "Linux"})
        r = subprocess.run([str(self.checkout / "scripts" / "novak"), "update", *args],
                           capture_output=True, text=True, env=env, timeout=120)
        import re
        return r.returncode, re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr)


class UpdateTests(unittest.TestCase):
    def test_update_pulls_the_checkout_before_the_images(self):
        d = Deployment(self)
        d.push_new_commit()
        self.assertFalse((d.checkout / "NEWFILE.txt").exists())
        code, out = d.update()
        self.assertEqual(code, 0, out)
        self.assertTrue((d.checkout / "NEWFILE.txt").exists())                     # adopted
        self.assertLess(out.index("Adopt"), out.index("Pulling images"))
        self.assertIn("STUB-PULL", out)
        self.assertNotIn("Run 'novak up' to apply any of this", out)               # update applies it itself

    def test_a_dirty_checkout_does_not_stop_the_image_update_and_is_said_plainly(self):
        d = Deployment(self)
        (d.checkout / "scratch.txt").write_text("my work in progress")
        d.push_new_commit()
        code, out = d.update()
        self.assertEqual(code, 0, out)
        self.assertIn("Adopt did not run", out)
        self.assertIn("uncommitted changes", out)
        self.assertIn("STUB-PULL", out)
        self.assertFalse((d.checkout / "NEWFILE.txt").exists())                    # nothing pulled over their work
        self.assertEqual((d.checkout / "scratch.txt").read_text(), "my work in progress")

    def test_no_adopt_skips_the_git_step(self):
        d = Deployment(self)
        d.push_new_commit()
        code, out = d.update("--no-adopt")
        self.assertEqual(code, 0, out)
        self.assertNotIn("Adopt", out)
        self.assertFalse((d.checkout / "NEWFILE.txt").exists())
        self.assertIn("STUB-PULL", out)

    def test_service_arguments_still_reach_the_pull(self):
        d = Deployment(self)
        code, out = d.update("ollama")
        self.assertEqual(code, 0, out)
        self.assertIn("STUB-PULL", out)


class CodeRevTests(unittest.TestCase):
    def test_revision_changes_only_when_the_watched_paths_do(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        git(root, "init", "-q", "-b", "main")
        (root / "gateway").mkdir()
        (root / "gateway" / "a.py").write_text("1")
        (root / "docs.md").write_text("1")
        git(root, "add", "-A"); git(root, "commit", "-q", "-m", "one")

        def rev(*paths):
            return subprocess.run(["bash", "-c", f"REPO_DIR={root}; source {REPO}/scripts/lib/rev.sh; code_rev {' '.join(paths)}"],
                                  capture_output=True, text=True).stdout.strip()

        before = rev("gateway")
        self.assertTrue(before)
        (root / "docs.md").write_text("2")
        git(root, "add", "-A"); git(root, "commit", "-q", "-m", "docs only")
        self.assertEqual(rev("gateway"), before)                 # an unrelated commit does not restart it
        (root / "gateway" / "a.py").write_text("2")
        git(root, "add", "-A"); git(root, "commit", "-q", "-m", "code")
        self.assertNotEqual(rev("gateway"), before)              # a change to its code does
        self.assertEqual(rev("nonexistent-dir"), "")


if __name__ == "__main__":
    unittest.main()


class HelperEnvironmentTests(unittest.TestCase):
    def test_every_python_helper_the_scripts_call_is_given_novak_home(self):
        """NOVAK_HOME is a plain shell variable in these scripts (resolved from $HOME or a
        marker file on Unraid), not an exported one, so a helper that reads the environment
        sees its own default (~/.novak) unless it is passed the value explicitly. Forgetting
        that left every registry-derived description in `novak secret list` blank on Spire,
        where the two differ. A static check, because the difference cannot be reproduced
        without a marker file."""
        import re as _re
        helper = _re.compile(r"reconciler/(instances|people|gateway_env|reconcile|omlx_apply|router_apply)\.py")
        missing = []
        for f in ["scripts/novak", "scripts/up.sh", "scripts/lib/vars.sh", "scripts/lib/secrets.sh"]:
            for n, line in enumerate((REPO / f).read_text().splitlines(), 1):
                code = line.split("#", 1)[0]
                if helper.search(code) and "python" in code.lower() or (helper.search(code) and '"$py"' in code):
                    if "NOVAK_HOME=" not in code and "NOVAK_HOME=" not in (REPO / f).read_text().splitlines()[n - 2]:
                        missing.append(f"{f}:{n}: {line.strip()[:110]}")
        self.assertEqual(missing, [], "these helper calls do not pass NOVAK_HOME:\n" + "\n".join(missing))
