"""Holding a destructive action until the person says yes.

The call is parked with its real arguments, the person is told, and the
requesting call waits (up to a timeout) for the answer. Approve runs it; deny
or silence does not. The link in the notification carries an unguessable
token, the same capability model as ingest's review page; the port is meant to
be tailnet-only.
"""
import json
import secrets
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token TEXT UNIQUE NOT NULL,
  person TEXT NOT NULL,
  entry TEXT NOT NULL,
  tool TEXT NOT NULL,
  args TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at INTEGER NOT NULL,
  decided_at INTEGER
);
"""


class Approvals:
    def __init__(self, path: str, clock=time.time):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.events: dict[int, threading.Event] = {}
        self.clock = clock
        with self.lock:
            self.db.executescript(SCHEMA)
            # Anything still pending belonged to a call that died with the last process.
            self.db.execute("UPDATE approvals SET status='expired' WHERE status='pending'")
            self.db.commit()

    def create(self, person, entry, tool, args) -> dict:
        token = secrets.token_urlsafe(24)
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO approvals(token,person,entry,tool,args,created_at) VALUES(?,?,?,?,?,?)",
                (token, person, entry, tool, json.dumps(args or {}), int(self.clock())))
            self.db.commit()
            self.events[cur.lastrowid] = threading.Event()
            return self.get(cur.lastrowid)

    def get(self, aid):
        with self.lock:
            row = self.db.execute("SELECT * FROM approvals WHERE id=?", (aid,)).fetchone()
        return dict(row) if row else None

    def by_token(self, token):
        with self.lock:
            row = self.db.execute("SELECT * FROM approvals WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None

    def decide(self, aid, approve: bool) -> bool:
        """True if this call made the decision (it can only be made once)."""
        with self.lock:
            cur = self.db.execute(
                "UPDATE approvals SET status=?, decided_at=? WHERE id=? AND status='pending'",
                ("approved" if approve else "denied", int(self.clock()), aid))
            self.db.commit()
            changed = cur.rowcount == 1
        if changed and aid in self.events:
            self.events[aid].set()
        return changed

    def wait(self, aid, timeout: float) -> str:
        """Blocks for the answer. Returns approved, denied or expired."""
        ev = self.events.get(aid)
        if ev:
            ev.wait(timeout)
        with self.lock:
            row = self.db.execute("SELECT status FROM approvals WHERE id=?", (aid,)).fetchone()
            if row["status"] == "pending":
                self.db.execute("UPDATE approvals SET status='expired' WHERE id=? AND status='pending'", (aid,))
                self.db.commit()
                return "expired"
        self.events.pop(aid, None)
        return row["status"]
