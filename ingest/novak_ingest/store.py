"""SQLite state: recordings and the task proposals derived from them."""
import json
import secrets
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS recordings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sha256 TEXT UNIQUE NOT NULL,
  source TEXT NOT NULL,
  recorded_at INTEGER NOT NULL,
  received_at INTEGER NOT NULL,
  filename TEXT NOT NULL,
  owner TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  title TEXT,
  note_path TEXT,
  progress TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS proposals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  recording_id INTEGER NOT NULL REFERENCES recordings(id),
  title TEXT NOT NULL,
  detail TEXT NOT NULL DEFAULT '',
  due TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  token TEXT UNIQUE NOT NULL,
  created_at INTEGER NOT NULL,
  decided_at INTEGER,
  result TEXT
);
"""
STATUSES = ("queued", "working", "done", "failed")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            cols = {r["name"] for r in self.db.execute("PRAGMA table_info(recordings)")}
            if "owner" not in cols:          # a database from before recordings had owners
                self.db.execute("ALTER TABLE recordings ADD COLUMN owner TEXT NOT NULL DEFAULT ''")
                self.db.commit()

    def _one(self, sql, args=()):
        with self.lock:
            row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _all(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _run(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    # recordings -----------------------------------------------------------
    def add_recording(self, sha256, source, recorded_at, filename, owner=""):
        """Returns (recording, created). A repeat upload is not a new job."""
        with self.lock:
            existing = self._one("SELECT * FROM recordings WHERE sha256=?", (sha256,))
            if existing:
                return existing, False
            cur = self._run(
                "INSERT INTO recordings(sha256,source,recorded_at,received_at,filename,owner)"
                " VALUES(?,?,?,?,?,?)",
                (sha256, source, int(recorded_at), int(time.time()), filename, owner),
            )
            return self.recording(cur.lastrowid), True

    def recording(self, rid):
        return self._one("SELECT * FROM recordings WHERE id=?", (rid,))

    def recordings(self, status=None, limit=100):
        if status:
            return self._all(
                "SELECT * FROM recordings WHERE status=? ORDER BY id DESC LIMIT ?",
                (status, limit),
            )
        return self._all("SELECT * FROM recordings ORDER BY id DESC LIMIT ?", (limit,))

    def next_queued(self):
        return self._one(
            "SELECT * FROM recordings WHERE status IN ('queued','working')"
            " ORDER BY recorded_at, id LIMIT 1"
        )

    def update_recording(self, rid, **fields):
        cols = ", ".join(f"{k}=?" for k in fields)
        self._run(f"UPDATE recordings SET {cols} WHERE id=?", (*fields.values(), rid))

    def progress(self, rid) -> dict:
        return json.loads(self.recording(rid)["progress"])

    def save_progress(self, rid, progress: dict):
        self.update_recording(rid, progress=json.dumps(progress))

    # proposals ------------------------------------------------------------
    def add_proposal(self, recording_id, title, detail="", due=None):
        token = secrets.token_urlsafe(24)
        cur = self._run(
            "INSERT INTO proposals(recording_id,title,detail,due,token,created_at)"
            " VALUES(?,?,?,?,?,?)",
            (recording_id, title, detail, due, token, int(time.time())),
        )
        return self.proposal(cur.lastrowid)

    def proposal(self, pid):
        return self._one("SELECT * FROM proposals WHERE id=?", (pid,))

    def proposal_by_token(self, token):
        return self._one("SELECT * FROM proposals WHERE token=?", (token,))

    def proposals(self, status=None):
        if status:
            return self._all(
                "SELECT * FROM proposals WHERE status=? ORDER BY id", (status,)
            )
        return self._all("SELECT * FROM proposals ORDER BY id DESC LIMIT 200")

    def decide(self, pid, status, result=""):
        """Only a pending proposal can be decided; returns whether this call did."""
        with self.lock:
            cur = self._run(
                "UPDATE proposals SET status=?, decided_at=?, result=?"
                " WHERE id=? AND status='pending'",
                (status, int(time.time()), result, pid),
            )
            return cur.rowcount == 1
