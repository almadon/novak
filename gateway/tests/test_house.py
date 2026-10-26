import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import tempfile
import unittest
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from novak_gateway import house  # noqa: E402
from novak_gateway.approvals import Approvals  # noqa: E402
from novak_gateway.audit import Audit  # noqa: E402
from novak_gateway.auth import Identity  # noqa: E402
from novak_gateway.homeassistant import HAClient, HAError  # noqa: E402
from novak_gateway.service import Gateway  # noqa: E402

# floor, area, id, name, state, brightness, rgb, supported_color_modes
ROWS = [
    ["Kata", "L1 Kitchen", "light.l1_bar", "L1 Bar", "on", 255, [255, 255, 255], ["rgb"]],
    ["Kata", "L2 Kitchen", "light.l2_bar", "Kitchen Bar", "on", 200, [255, 120, 0], ["rgb"]],
    ["Kata", "L2 Kitchen", "light.l2_relay", "Kitchen Relay", "on", None, None, ["onoff"]],
    ["Kata", "L2 Living Room", "light.l2_lamp", "Corner Lamp", "on", 128, [10, 20, 30], ["xy"]],
    ["Kata", "L2 Living Room", "light.l2_strip", "TV Strip", "off", None, None, ["rgb"]],
    ["Kata", "L2 Living Room", "light.l2_gone", "Old Lamp", "unavailable", None, None, ["rgb"]],
    ["Alsos", "Entry", "light.entry", "Entry Light", "off", None, None, ["brightness"]],
]


class FakeHA:
    """Stands in for the person's Home Assistant MCP entry."""

    def __init__(self, rows=ROWS, fail=()):
        self.rows, self.fail, self.calls = rows, set(fail), []

    def call(self, method, params=None):
        if method == "tools/list":
            return {"tools": []}
        name, args = params["name"], params["arguments"]
        if name == "ha_eval_template":
            return {"content": [{"type": "text", "text": json.dumps({"success": True, "result": json.dumps(self.rows)})}]}
        if name == "ha_call_service":
            self.calls.append(args)
            if args["entity_id"] in self.fail:
                return {"isError": True, "content": [{"type": "text", "text": '{"success": false, "error": "boom"}'}]}
            return {"content": [{"type": "text", "text": '{"success": true}'}]}
        raise AssertionError(name)


class HouseTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": [
            {"name": "ha-mcp", "kind": "external", "url": "http://ha/mcp", "enabled": True},
            {"name": "hs-ushy", "kind": "external", "url": "http://hs/mcp", "enabled": True}]}))
        (self.dir / "people.yaml").write_text(yaml.safe_dump({
            "people": {"tmeuze": {"names": ["tmeuze"], "entries": ["ha-mcp"]},
                       "ushy": {"names": ["ushy"], "entries": ["hs-ushy"]}},
            "household": {"entries": []}}))
        (self.dir / "gateway.yaml").write_text(yaml.safe_dump({"gateway": {"house": {"entry": "ha-mcp"}}}))   # the older route
        self.ha = FakeHA()
        self.gw = Gateway(self.dir, Audit(str(self.dir / "a.db")), Approvals(str(self.dir / "p.db")), "http://gw", {},
                          notifier=lambda *a: "x", upstream_factory=lambda url, token: self.ha)
        self.me = Identity("person", "tmeuze", "key", self.gw.dir.find_person("tmeuze"))
        self.ushy = Identity("person", "ushy", "key", self.gw.dir.find_person("ushy"))

    def call(self, tool, args=None, who=None):
        r = self.gw.call_tool(who or self.me, f"house__{tool}", args or {})
        return r["content"][0]["text"], r.get("isError", False)

    # who gets them ----------------------------------------------------------------------------
    def test_only_a_person_with_a_home_assistant_entry_is_offered_the_tools(self):
        self.assertEqual({t["name"] for t in self.gw.list_tools(self.me)} & {"house__house_state", "house__lights_set"},
                         {"house__house_state", "house__lights_set"})
        self.assertEqual([t["name"] for t in self.gw.list_tools(self.ushy) if t["name"].startswith("house__")], [])
        text, err = self.call("house_state", who=self.ushy)
        self.assertTrue(err)
        self.assertIn("Unknown tool", text)

    def test_they_are_small(self):
        size = len(json.dumps(house.TOOLS))
        self.assertLess(size, 1800)                                    # a few hundred tokens, not twenty thousand

    def test_a_scope_that_does_not_name_house_hides_them_and_one_that_does_keeps_them(self):
        names = lambda ident: [t["name"] for t in self.gw.list_tools(ident) if t["name"].startswith("house__")]
        self.me.scope = ("hs-*",)
        self.assertEqual(names(self.me), [])
        self.me.scope = ("ha-*", "house")
        self.assertEqual(len(names(self.me)), 2)

    def test_a_tool_allowlist_narrows_everything_including_the_house_tools(self):
        self.me.tools = ("house__*",)
        self.assertEqual({t["name"] for t in self.gw.list_tools(self.me)}, {"house__house_state", "house__lights_set"})
        self.me.tools = ("house__house_state",)
        self.assertEqual([t["name"] for t in self.gw.list_tools(self.me)], ["house__house_state"])
        text, err = self.call("lights_set", {"where": "all"})
        self.assertTrue(err)
        self.assertEqual(self.ha.calls, [])

    # reading ------------------------------------------------------------------------------------
    def test_the_state_names_floors_areas_and_what_is_on(self):
        text, err = self.call("house_state")
        self.assertFalse(err)
        self.assertIn("Kata (L1 Kitchen 1/1, L2 Kitchen 2/2, L2 Living Room 1/3)", text)
        self.assertIn("Alsos (Entry 0/1)", text)
        self.assertIn("Kata / L2 Kitchen: Kitchen Bar 78% rgb(255,120,0); Kitchen Relay", text)
        self.assertNotIn("light.", text)                                # no ids to confuse a small model

    def test_looking_at_one_floor_by_a_loose_name(self):
        text, _ = self.call("house_state", {"where": "floor 2"})
        self.assertIn("L2 Kitchen", text)
        self.assertNotIn("L1 Kitchen", text)
        self.assertNotIn("Alsos", text)

    def test_an_unknown_place_says_what_exists(self):
        text, err = self.call("house_state", {"where": "the moon"})
        self.assertTrue(err)
        self.assertIn("L2 Kitchen", text)

    # acting -----------------------------------------------------------------------------------------
    def test_dimming_the_lights_that_are_on_and_coloring_them_individually(self):
        text, err = self.call("lights_set", {"where": "floor 2", "brightness_pct": 30,
                                             "colors": ["#ff71ce", "1,205,254", "#b967ff"]})
        self.assertFalse(err)
        by_id = {c["entity_id"]: c for c in self.ha.calls}
        self.assertEqual(set(by_id), {"light.l2_bar", "light.l2_relay", "light.l2_lamp"})    # on, on floor 2, not the off/unavailable ones
        self.assertEqual(by_id["light.l2_bar"]["data"], {"brightness_pct": 30, "rgb_color": [255, 113, 206]})
        self.assertEqual(by_id["light.l2_lamp"]["data"]["rgb_color"], [1, 205, 254])         # the next color, in turn
        self.assertEqual(by_id["light.l2_relay"]["data"], {"brightness_pct": 30})              # on/off only: dimmed, never colored
        self.assertTrue(all(c["domain"] == "light" and c["service"] == "turn_on" and c["wait"] is False for c in self.ha.calls))
        self.assertIn("3 light(s) set in floor 2 at 30%", text)

    def test_colors_cycle_when_there_are_more_lights_than_colors(self):
        self.ha.rows = [["Kata", "L2 A", f"light.a{i}", f"A{i}", "on", 255, [0, 0, 0], ["rgb"]] for i in range(5)]
        self.call("lights_set", {"where": "L2 A", "colors": ["#ff0000", "#00ff00"]})
        self.assertEqual([c["data"]["rgb_color"] for c in self.ha.calls],
                         [[255, 0, 0], [0, 255, 0], [255, 0, 0], [0, 255, 0], [255, 0, 0]])

    def test_nothing_on_says_so_and_says_how_to_turn_them_on(self):
        self.ha.rows = [r[:4] + ["off"] + r[5:] for r in ROWS]
        text, err = self.call("lights_set", {"where": "floor 2", "brightness_pct": 30})
        self.assertTrue(err)
        self.assertIn("No lights are on in floor 2", text)
        self.assertIn("which='all'", text)
        self.assertEqual(self.ha.calls, [])
        text, err = self.call("lights_set", {"where": "floor 2", "which": "all", "brightness_pct": 30})
        self.assertFalse(err)
        self.assertEqual(len(self.ha.calls), 5)                       # all of floor 2 except the unavailable one

    def test_turning_lights_off(self):
        self.call("lights_set", {"where": "L2 Kitchen", "state": "off"})
        self.assertEqual([(c["service"], c["entity_id"]) for c in self.ha.calls],
                         [("turn_off", "light.l2_bar"), ("turn_off", "light.l2_relay")])
        self.assertTrue(all("data" not in c for c in self.ha.calls))

    def test_a_partial_failure_is_reported_and_all_failing_is_an_error(self):
        self.ha.fail = {"light.l2_relay"}
        text, err = self.call("lights_set", {"where": "L2 Kitchen", "brightness_pct": 20})
        self.assertFalse(err)
        self.assertIn("1 failed: Kitchen Relay", text)
        self.ha.fail = {"light.l2_bar", "light.l2_relay"}
        self.assertTrue(self.call("lights_set", {"where": "L2 Kitchen", "brightness_pct": 20})[1])

    def test_bad_input_is_refused_with_a_hint_and_touches_nothing(self):
        for args in ({}, {"where": "all", "colors": ["notacolor"]}, {"where": "all", "brightness_pct": "dim"},
                     {"where": "all", "state": "dim"}, {"where": "nowhere at all"}):
            text, err = self.call("lights_set", args)
            self.assertTrue(err, args)
        self.assertEqual(self.ha.calls, [])
        self.assertIn("hex", self.call("lights_set", {"where": "all", "colors": ["notacolor"]})[0])

    def test_brightness_is_kept_in_range(self):
        self.call("lights_set", {"where": "L1 Kitchen", "brightness_pct": 400})
        self.assertEqual(self.ha.calls[0]["data"]["brightness_pct"], 100)

    def test_the_audit_records_who_and_what_as_the_house_entry(self):
        self.call("lights_set", {"where": "L2 Kitchen", "brightness_pct": 20})
        self.call("house_state")
        rows = self.gw.audit.recent("tmeuze")
        seen = {(r["entry"], r["tool"], r["kind"], r["decision"]) for r in rows}
        self.assertIn(("house", "lights_set", "modify", "allowed"), seen)
        self.assertIn(("house", "house_state", "read", "allowed"), seen)

    def test_an_unreachable_home_assistant_is_an_error_not_a_crash(self):
        def boom(*a):
            raise OSError("down")
        self.ha.call = boom
        text, err = self.call("house_state")
        self.assertTrue(err)
        self.assertIn("could not reach", text)

    # parsing ------------------------------------------------------------------------------------------
    def test_colors_in_each_accepted_spelling(self):
        for given, want in (("#ff71ce", (255, 113, 206)), ("ff71ce", (255, 113, 206)), ("1,205,254", (1, 205, 254)),
                            ("[5, 255, 161]", (5, 255, 161)), ([185, 103, 255], (185, 103, 255)), ("256,0,0", None), ("red", None)):
            self.assertEqual(house.parse_color(given), want, given)


class FakeRest:
    """Stands in for HAClient: the direct route, with the service admin token."""

    def __init__(self, url, token, rows=ROWS, fail=()):
        self.url, self.token, self.rows, self.fail, self.calls = url, token, rows, set(fail), []

    def template(self, template):
        return json.dumps(self.rows)

    def call_service(self, domain, service, entity_id, data=None):
        self.calls.append((domain, service, entity_id, data or {}))
        if entity_id in self.fail:
            raise HAError("Home Assistant answered 400: boom")


class DirectRouteTests(unittest.TestCase):
    """House tools straight to Home Assistant with HA_<id>_ADMIN_API_TOKEN (decision #77)."""

    def make(self, env, house=None):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.dir, ignore_errors=True))
        (self.dir / "mcp-servers.yaml").write_text(yaml.safe_dump({"servers": [
            {"name": "ha-mcp", "kind": "external", "url": "http://ha/mcp", "enabled": True}]}))
        (self.dir / "people.yaml").write_text(yaml.safe_dump({
            "people": {"tmeuze": {"names": ["tmeuze"], "entries": ["ha-mcp"]},
                       "ushy": {"names": ["ushy"], "entries": []}},
            "household": {"entries": []}}))
        (self.dir / "gateway.yaml").write_text(yaml.safe_dump({"gateway": {"house": house or {"ha": 1, "people": ["tmeuze"]}}}))
        self.made = []
        def factory(url, token):
            c = FakeRest(url, token)
            self.made.append(c)
            return c
        gw = Gateway(self.dir, Audit(str(self.dir / "a.db")), Approvals(str(self.dir / "p.db")), "http://gw", env,
                     notifier=lambda *a: "x", ha_factory=factory,
                     upstream_factory=lambda url, token: self.fail("the ha-mcp route must not be used"))
        return gw, Identity("person", "tmeuze", "key", gw.dir.find_person("tmeuze")), Identity("person", "ushy", "key", gw.dir.find_person("ushy"))

    ENV = {"HA_1_URL": "http://xenia", "HA_1_ADMIN_API_TOKEN": "tok"}

    def test_it_uses_the_instance_url_and_service_token_and_never_the_mcp_entry(self):
        gw, me, _ = self.make(self.ENV)
        r = gw.call_tool(me, "house__lights_set", {"where": "L2 Kitchen", "brightness_pct": 30})
        self.assertFalse(r.get("isError"))
        self.assertEqual((self.made[0].url, self.made[0].token), ("http://xenia", "tok"))
        self.assertEqual(self.made[0].calls, [("light", "turn_on", "light.l2_bar", {"brightness_pct": 30}),
                                              ("light", "turn_on", "light.l2_relay", {"brightness_pct": 30})])

    def test_only_the_people_named_get_the_tools(self):
        gw, me, ushy = self.make(self.ENV)
        self.assertIn("house__house_state", [t["name"] for t in gw.list_tools(me)])
        self.assertNotIn("house__house_state", [t["name"] for t in gw.list_tools(ushy)])
        self.assertTrue(gw.call_tool(ushy, "house__house_state", {}).get("isError"))

    def test_without_the_token_the_tools_are_not_offered(self):
        gw, me, _ = self.make({"HA_1_URL": "http://xenia"})
        self.assertNotIn("house__house_state", [t["name"] for t in gw.list_tools(me)])

    def test_a_failure_from_home_assistant_is_reported_not_raised(self):
        gw, me, _ = self.make(self.ENV)
        gw.ha_factory = lambda url, token: FakeRest(url, token, fail={"light.l2_bar", "light.l2_relay"})
        r = gw.call_tool(me, "house__lights_set", {"where": "L2 Kitchen", "brightness_pct": 20})
        self.assertTrue(r["isError"])
        self.assertIn("boom", r["content"][0]["text"])


class HAClientTests(unittest.TestCase):
    def setUp(self):
        seen = self.seen = []
        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                seen.append((self.path, self.headers["Authorization"], body))
                code = 401 if self.headers["Authorization"] == "Bearer bad" else 200
                out = b"[]" if self.path == "/api/template" else b"[]"
                self.send_response(code); self.end_headers(); self.wfile.write(b"nope" if code == 401 else out)
            def log_message(self, *a): pass
        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.shutdown)
        self.url = f"http://127.0.0.1:{self.srv.server_port}"

    def test_the_two_calls_send_the_token_and_the_expected_bodies(self):
        c = HAClient(self.url, "good")
        self.assertEqual(c.template("{{ 1 }}"), "[]")
        c.call_service("light", "turn_on", "light.a", {"brightness_pct": 5})
        self.assertEqual(self.seen, [("/api/template", "Bearer good", {"template": "{{ 1 }}"}),
                                     ("/api/services/light/turn_on", "Bearer good", {"entity_id": "light.a", "brightness_pct": 5})])

    def test_a_refused_token_says_it_must_be_an_admin(self):
        with self.assertRaises(HAError) as ctx:
            HAClient(self.url, "bad").template("{{ 1 }}")
        self.assertIn("admin", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
