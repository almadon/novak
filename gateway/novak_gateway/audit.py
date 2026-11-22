"""Accounting: who did what, when, with what outcome.

Records the person, how they were identified, the entry and tool, the kind of
action, the decision and the outcome. Never the arguments or results (they can
hold anything a person said or stored), only the argument names.
"""
import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  person TEXT NOT NULL,
  via TEXT NOT NULL,
  entry TEXT,
  tool TEXT,
  kind TEXT,
  decision TEXT NOT NULL,
  outcome TEXT,
  ms INTEGER,
  arg_names TEXT
);
CREATE INDEX IF NOT EXISTS audit_person ON audit(person, ts);
"""


class Audit:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.db.executescript(SCHEMA)

    def record(self, identity, entry, tool, kind, decision, outcome="", ms=0, args=None):
        names = json.dumps(sorted((args or {}).keys()))
        with self.lock:
            self.db.execute(
                "INSERT INTO audit(ts,person,via,entry,tool,kind,decision,outcome,ms,arg_names)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (int(time.time()), identity.name, identity.via, entry, tool, kind, decision,
                 str(outcome)[:200], int(ms), names))
            self.db.commit()

    def recent(self, person=None, limit=50):
        sql, args = "SELECT * FROM audit", ()
        if person:
            sql, args = sql + " WHERE person=?", (person,)
        with self.lock:
            rows = self.db.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit)).fetchall()
        return [dict(r) for r in rows]

    def summary(self, since: int, person=None, recent=25):
        """What a status page needs, and nothing a person said: counts since a moment, and the latest rows."""
        where, args = "ts>=?", [since]
        if person:
            where, args = where + " AND person=?", [*args, person]
        with self.lock:
            by_decision = {r["decision"]: r["n"] for r in self.db.execute(
                f"SELECT decision, COUNT(*) n FROM audit WHERE {where} GROUP BY decision", args)}
            errors = self.db.execute(
                f"SELECT COUNT(*) n FROM audit WHERE {where} AND outcome LIKE 'error%'", args).fetchone()["n"]
            by_person = {r["person"]: r["n"] for r in self.db.execute(
                f"SELECT person, COUNT(*) n FROM audit WHERE {where} GROUP BY person ORDER BY n DESC", args)}
            rows = self.db.execute(
                "SELECT ts,person,via,entry,tool,kind,decision,outcome,ms FROM audit"
                + (" WHERE person=?" if person else "") + " ORDER BY id DESC LIMIT ?",
                ([person] if person else []) + [recent]).fetchall()
        return {"since": since, "calls": sum(by_decision.values()), "by_decision": by_decision,
                "errors": errors, "by_person": by_person, "recent": [dict(r) for r in rows]}
