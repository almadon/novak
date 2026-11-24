import json
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "reconciler"))
import backup  # noqa: E402

SECRET = "sk-very-secret-value"
PG_DUMP = b"PGDMP" + b"x" * 2000


def make_db(path: Path, rows=3, wal=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    if wal:
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t (n INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])
    con.commit()
    return con


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.root, ignore_errors=True))
        self.home = self.root / "home"
        (self.home / "registry" / "profiles").mkdir(parents=True)
        (self.home / "registry" / "people.yaml").write_text("people: {}\n")
        (self.home / "registry" / "people.yaml.bak-20261001").write_text("old\n")
        (self.home / "registry" / "profiles" / "tmeuze.md").write_text("Be brief.\n")
        (self.home / ".env").write_text("HOST_NAME=spire\n")
        (self.home / "secrets.env").write_text(f"WEBUI_SECRET_KEY={SECRET}\n")
        os.chmod(self.home / "secrets.env", 0o600)
        (self.home / "models").mkdir()
        (self.home / "models" / "big.bin").write_text("x" * 100)
        self.keep = make_db(self.home / "data" / "open-webui" / "webui.db", rows=5, wal=True)   # left open, as a running app would
        (self.home / "data" / "open-webui" / "uploads").mkdir()
        (self.home / "data" / "open-webui" / "uploads" / "a.txt").write_text("hello")
        make_db(self.home / "data" / "ingest" / "ingest.db").close()
        (self.home / "data" / "ingest" / "audio").mkdir()
        (self.home / "data" / "ingest" / "audio" / "r1.wav").write_text("riff")
        self.vol = self.root / "volume"
        make_db(self.vol / "audit.db", rows=2).close()
        make_db(self.vol / "approvals.db", rows=1).close()
        self.addCleanup(self.keep.close)
        self.calls = []
        self.pg_ok = True
        self.dest = self.root / "staging"

    # fakes for docker ----------------------------------------------------------------------------
    def runner(self, cmd):
        self.calls.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            return SimpleNamespace(returncode=0, stdout=b"abc123\n", stderr=b"")
        if cmd[:3] == ["docker", "volume", "inspect"]:
            return SimpleNamespace(returncode=0, stdout=f"{self.vol}\n".encode(), stderr=b"")
        raise AssertionError(cmd)

    def streamer(self, cmd, dst):
        self.calls.append(cmd)
        if not self.pg_ok:
            return 1, "pg_dump: connection refused"
        dst.write_bytes(PG_DUMP)
        return 0, ""

    def run_backup(self, *extra):
        lines = []
        env = {"NOVAK_HOME": str(self.home)}
        code = backup.main(["--dest", str(self.dest), *extra], env=env, runner=self.runner,
                           streamer=self.streamer, out=lines.append)
        return code, "\n".join(lines)

    # what is in the copy -----------------------------------------------------------------------------
    def test_it_copies_what_matters_and_leaves_out_models_and_dated_backups(self):
        code, out = self.run_backup()
        self.assertEqual(code, 0, out)
        d = self.dest
        self.assertTrue((d / "files" / ".env").is_file())
        self.assertEqual((d / "files" / "secrets.env").read_text(), f"WEBUI_SECRET_KEY={SECRET}\n")
        self.assertTrue((d / "registry" / "profiles" / "tmeuze.md").is_file())
        self.assertFalse((d / "registry" / "people.yaml.bak-20261001").exists())
        self.assertFalse((d / "models").exists())
        self.assertEqual((d / "data" / "open-webui" / "uploads" / "a.txt").read_text(), "hello")
        self.assertTrue((d / "data" / "ingest" / "audio" / "r1.wav").is_file())
        self.assertEqual((d / "hindsight.dump").read_bytes(), PG_DUMP)

    def test_the_databases_are_consistent_copies_not_plain_file_copies(self):
        self.keep.execute("INSERT INTO t VALUES (99)")       # committed but possibly still only in the WAL
        self.keep.commit()
        self.run_backup()
        for rel, n in (("data/open-webui/webui.db", 6), ("data/ingest/ingest.db", 3),
                       ("gateway-data/audit.db", 2), ("gateway-data/approvals.db", 1)):
            con = sqlite3.connect(self.dest / rel)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM t").fetchone()[0], n, rel)
            con.close()
        self.assertEqual(sorted(p.name for p in (self.dest / "data" / "open-webui").iterdir()), ["uploads", "webui.db"])

    def test_the_copy_is_private(self):
        self.run_backup()
        self.assertEqual(stat.S_IMODE(self.dest.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.dest / "files" / "secrets.env").stat().st_mode), 0o600)

    def test_the_manifest_has_sizes_and_no_secret_and_the_output_prints_none(self):
        code, out = self.run_backup()
        manifest = json.loads((self.dest / "manifest.json").read_text())
        self.assertIn("files/secrets.env", manifest["items"])
        self.assertGreater(manifest["total_bytes"], 0)
        self.assertNotIn(SECRET, (self.dest / "manifest.json").read_text())
        self.assertNotIn(SECRET, out)

    def test_the_password_for_postgres_is_never_on_a_command_line(self):
        self.run_backup()
        dump = next(c for c in self.calls if c[:2] == ["docker", "exec"])
        self.assertEqual(dump[2], "abc123")
        self.assertIn("instance.json", dump[-1])               # read inside the container
        self.assertNotIn("PGPASSWORD=", " ".join(c for c in dump[:-1]))

    # replacing the old copy ---------------------------------------------------------------------------
    def test_a_second_run_replaces_the_first_and_keeps_only_one(self):
        self.run_backup()
        (self.home / ".env").write_text("HOST_NAME=changed\n")
        self.run_backup()
        self.assertEqual((self.dest / "files" / ".env").read_text(), "HOST_NAME=changed\n")
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith("staging")), ["staging"])

    def test_a_failure_exits_non_zero_and_leaves_the_previous_copy_untouched(self):
        self.run_backup()
        before = (self.dest / "files" / ".env").read_text()
        (self.home / ".env").write_text("HOST_NAME=would-be-new\n")
        self.pg_ok = False
        code, _ = self.run_backup()
        self.assertEqual(code, 1)
        self.assertEqual((self.dest / "files" / ".env").read_text(), before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if p.name.startswith("staging")), ["staging"])

    def test_a_failed_first_run_leaves_nothing_to_back_up(self):
        self.pg_ok = False
        code, _ = self.run_backup()
        self.assertEqual(code, 1)
        self.assertFalse(self.dest.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith("staging")], [])

    def test_an_unfinished_earlier_run_is_cleaned_up(self):
        stale = self.root / "staging.tmp-20200101T000000Z"
        stale.mkdir()
        (stale / "half").write_text("x")
        self.assertEqual(self.run_backup()[0], 0)
        self.assertFalse(stale.exists())

    def test_an_empty_dump_is_a_failure(self):
        orig = self.streamer
        self.streamer = lambda cmd, dst: (dst.write_bytes(b"") or 0, "")
        self.assertEqual(self.run_backup()[0], 1)
        self.streamer = orig

    def test_a_wrong_home_is_an_error_not_an_empty_backup(self):
        shutil_home = self.home / "registry"
        __import__("shutil").rmtree(shutil_home)
        self.assertEqual(self.run_backup()[0], 1)
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
