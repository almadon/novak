import json
import time
import unittest
import urllib.error
import urllib.request

import yaml

from novak_gateway.directory import sha256

from test_gateway import World

ADMIN, CHANGE = "admin-key-eeeeeeeeeeee", "change-key-ffffffffffff"
MID = "0a1b2c3d-0000-4000-8000-000000000001"


def world(test, timeout=5):
    w = World(test, confirm_timeout=timeout,
              settings={"admin": {"key_sha256": sha256(ADMIN), "change_key_sha256": sha256(CHANGE)}})
    # Give tmeuze the conventionally named memory entry, pointing at the fake backend.
    servers = yaml.safe_load((w.dir / "mcp-servers.yaml").read_text())["servers"]
    srv = next(s for s in servers if s["name"] == "hs-tmeuze")
    servers.append({**srv, "name": "hindsight-tmeuze"})
    (w.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": servers}))
    people = yaml.safe_load((w.dir / "people.yaml").read_text())
    people["people"]["tmeuze"]["entries"].append("hindsight-tmeuze")
    (w.dir / "people.yaml").write_text(yaml.safe_dump(people))
    time.sleep(0.05)
    return w


def post(w, body, key=CHANGE):
    req = urllib.request.Request(w.base + "/admin/changes", data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def until(fn, seconds=4):
    end = time.time() + seconds
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(0.05)
    return None


def calls(w):
    return [p for m, a, p in w.seen["hs-tmeuze"] if m == "tools/call" and p["name"] == "invalidate_memory"]


ASK = {"person": "tmeuze", "action": "forget_memory", "bank": "tmeuze", "memory_id": MID}


class ChangeTests(unittest.TestCase):
    def test_only_the_change_key_opens_it(self):
        w = world(self)
        for k in (None, ADMIN, w.keys["tmeuze"], w.keys["owui"]):
            self.assertEqual(post(w, ASK, k)[0], 401, k)
        self.assertEqual(w.approvals.listing()["pending"], [])

    def test_the_status_key_cannot_ask_and_the_change_key_cannot_read_status(self):
        w = world(self)
        req = urllib.request.Request(w.base + "/admin/today", headers={"Authorization": f"Bearer {CHANGE}"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 401)

    def test_nothing_happens_until_the_person_says_yes(self):
        w = world(self)
        self.assertEqual(post(w, ASK), (202, {"status": "asked"}))
        pending = until(lambda: w.approvals.listing()["pending"])
        self.assertTrue(pending)
        self.assertEqual((pending[0]["person"], pending[0]["tool"]), ("tmeuze", "invalidate_memory"))
        self.assertEqual(calls(w), [])                         # asked, not done
        self.assertTrue(until(lambda: w.notes))                # and their phone was told
        w.approvals.decide(pending[0]["id"], True)
        done = until(lambda: calls(w))
        self.assertEqual(done[0]["arguments"]["memory_id"], MID)
        row = until(lambda: [r for r in w.audit.recent("tmeuze") if r["decision"] == "approved"])
        self.assertEqual((row[0]["via"], row[0]["entry"]), ("console", "hindsight-tmeuze"))

    def test_a_no_changes_nothing(self):
        w = world(self)
        post(w, ASK)
        pending = until(lambda: w.approvals.listing()["pending"])
        w.approvals.decide(pending[0]["id"], False)
        self.assertTrue(until(lambda: [r for r in w.audit.recent("tmeuze") if r["decision"] == "denied"]))
        self.assertEqual(calls(w), [])

    def test_silence_expires_and_changes_nothing(self):
        w = world(self, timeout=0.3)
        post(w, ASK)
        self.assertTrue(until(lambda: [r for r in w.audit.recent("tmeuze") if r["decision"] == "expired"]))
        self.assertEqual(calls(w), [])

    def test_only_a_persons_own_banks_and_ids_of_the_right_shape(self):
        w = world(self)
        self.assertEqual(post(w, {**ASK, "bank": "ushy"})[0], 403)
        self.assertEqual(post(w, {**ASK, "bank": "household"})[0], 403)
        self.assertEqual(post(w, {**ASK, "bank": "../x"})[0], 403)
        self.assertEqual(post(w, {**ASK, "memory_id": "x; drop"})[0], 400)
        self.assertEqual(post(w, {**ASK, "action": "delete_everything"})[0], 400)
        self.assertEqual(post(w, {**ASK, "person": "nobody"})[0], 404)
        self.assertEqual(post(w, {**ASK, "person": "ushy"})[0], 403)    # ushy has no tmeuze bank
        self.assertEqual(w.approvals.listing()["pending"], [])

    def test_a_flood_is_stopped_at_three_waiting(self):
        w = world(self, timeout=30)
        codes = []
        for i in range(5):
            codes.append(post(w, {**ASK, "memory_id": f"0a1b2c3d-0000-4000-8000-00000000000{i}"})[0])
            until(lambda: len(w.approvals.listing()["pending"]) >= min(i + 1, 3), 2)
        self.assertEqual(codes, [202, 202, 202, 429, 429])
        for p in w.approvals.listing()["pending"]:                # let the waiting threads finish
            w.approvals.decide(p["id"], False)
        until(lambda: len([r for r in w.audit.recent("tmeuze") if r["decision"] == "denied"]) >= 3, 3)


if __name__ == "__main__":
    unittest.main()
