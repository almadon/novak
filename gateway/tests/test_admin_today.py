import json
import unittest
import urllib.error
import urllib.request

from novak_gateway.directory import sha256

from test_gateway import World

ADMIN = "admin-key-eeeeeeeeeeee"


def get(w, path, key=None):
    req = urllib.request.Request(w.base + path, headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def world(test):
    return World(test, settings={"admin": {"key_sha256": sha256(ADMIN)}})


class AdminTodayTests(unittest.TestCase):
    def test_needs_the_admin_key_and_no_other_key_will_do(self):
        w = world(self)
        self.assertEqual(get(w, "/admin/today")[0], 401)
        for k in ("tmeuze", "household", "owui"):
            self.assertEqual(get(w, "/admin/today", w.keys[k])[0], 401, k)
        self.assertEqual(get(w, "/admin/today", ADMIN)[0], 200)

    def test_closed_when_no_admin_key_is_configured(self):
        w = World(self)
        self.assertEqual(get(w, "/admin/today", "")[0], 401)
        self.assertEqual(get(w, "/admin/today", ADMIN)[0], 401)

    def test_the_admin_key_opens_nothing_else(self):
        w = world(self)
        self.assertEqual(w.tools(token=ADMIN)[0], 401)
        self.assertEqual(w.call("hs_tmeuze__recall", token=ADMIN)[0], 401)

    def test_counts_activity_and_never_shows_arguments_or_tokens(self):
        w = world(self)
        w.call("hs_tmeuze__recall", {"query": "my secret thought"}, token=w.keys["tmeuze"])
        w.call("hs_tmeuze__recall", token=w.keys["ushy"])          # denied
        w.approvals.create("tmeuze", "hs-tmeuze", "delete_document", {"id": "private-doc"})
        code, r = get(w, "/admin/today", ADMIN)
        self.assertEqual(code, 200)
        self.assertEqual(r["activity"]["calls"], 2)
        self.assertEqual(r["activity"]["by_decision"], {"allowed": 1, "denied": 1})
        self.assertEqual(len(r["approvals"]["pending"]), 1)
        self.assertEqual(r["approvals"]["pending"][0]["tool"], "delete_document")
        raw = json.dumps(r)
        for secret in ("my secret thought", "private-doc", "token", w.approvals.get(1)["token"]):
            self.assertNotIn(secret, raw)

    def test_can_be_narrowed_to_one_person(self):
        w = world(self)
        w.call("hs_tmeuze__recall", token=w.keys["tmeuze"])
        w.call("hs_ushy__recall", token=w.keys["ushy"])
        w.approvals.create("ushy", "hs-ushy", "delete_document", {})
        _, r = get(w, "/admin/today?person=tmeuze", ADMIN)
        self.assertEqual(r["activity"]["calls"], 1)
        self.assertEqual({x["person"] for x in r["activity"]["recent"]}, {"tmeuze"})
        self.assertEqual(r["approvals"]["pending"], [])
        self.assertEqual(get(w, "/admin/today?person=nobody", ADMIN)[0], 404)


if __name__ == "__main__":
    unittest.main()
