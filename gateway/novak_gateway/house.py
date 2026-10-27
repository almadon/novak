"""Lean house tools: two small tools in place of Home Assistant's seventy-odd (decision #71).

The generic Home Assistant tools are about 21,000 tokens of definitions for the house alone, against
a model context of 8,192. A model given them loses the start of its prompt, invents arguments (floor
ids, areas) and goes quiet after the first error. These tools are about 250 tokens in all and do the
looking-up themselves: the model says "floor 2" and "vaporwave colours", and the gateway resolves the
lights and makes the calls.

They run on one Home Assistant instance, named by id in `gateway.yaml` (`house: {ha: 1, people: [...]}`),
with that instance's service admin token (`HA_<id>_ADMIN_API_TOKEN`; address `GATEWAY_HA_URL`, or `HA_<id>_URL` to override), and only
ever touch lights, so nothing here needs a person's confirmation.
"""
import json
import re
import time

SEP = "__"
ALIAS = "house"
MAX_LIGHTS_SHOWN = 40
MAX_COLORS = 12

# One request for every light that is not a group, with where it is and how it is set.
SNAPSHOT_TEMPLATE = (
    "{% set ns = namespace(rows=[]) %}"
    "{% for f in floors() %}{% for a in floor_areas(f) %}"
    "{% for e in area_entities(a) if e.startswith('light.') and state_attr(e,'entity_id') is none %}"
    "{% set ns.rows = ns.rows + [[floor_name(f), area_name(a), e, states[e].name, states(e), "
    "state_attr(e,'brightness'), state_attr(e,'rgb_color'), state_attr(e,'supported_color_modes')]] %}"
    "{% endfor %}{% endfor %}{% endfor %}{{ ns.rows | tojson }}")

COLOR_MODES = {"rgb", "rgbw", "rgbww", "hs", "xy"}

TOOLS = [
    {"name": "house_state",
     "description": "What the lights are doing: floors, areas, which lights are on and how. "
                    "Call once to see the house; call again after changes or when asked.",
     "inputSchema": {"type": "object", "properties": {
         "where": {"type": "string", "description": "A floor or area name to look at. Omit for the whole house."}}}},
    {"name": "lights_set",
     "description": "Change lights by floor or area name; no ids needed. By default only lights that are "
                    "on. Give colors to color the lights individually (cycled across them).",
     "inputSchema": {"type": "object", "required": ["where"], "properties": {
         "where": {"type": "string", "description": "Floor or area name(s), comma separated, e.g. 'floor 2' or 'L2 Kitchen'. 'all' for everywhere."},
         "state": {"type": "string", "enum": ["on", "off"], "description": "Default on."},
         "which": {"type": "string", "enum": ["on", "all"], "description": "'on' (default): only lights now on. 'all': every light there."},
         "brightness_pct": {"type": "integer", "description": "1 to 100."},
         "colors": {"type": "array", "items": {"type": "string"},
                    "description": "Hex like '#ff71ce' or 'r,g,b'. Each light takes the next color in turn."}}}},
]


def _text(msg: str, error=False) -> dict:
    return {"content": [{"type": "text", "text": msg}], "isError": error}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def parse_color(value) -> tuple | None:
    """'#ff71ce', 'ff71ce', '255,113,206' or [r, g, b] -> (r, g, b), or None when it is not a color."""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        parts = list(value)
    else:
        s = str(value).strip()
        m = re.fullmatch(r"#?([0-9a-fA-F]{6})", s)
        if m:
            h = m.group(1)
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        parts = [p for p in re.split(r"[,\s]+", s.strip("[]() ")) if p]
    try:
        rgb = tuple(int(float(p)) for p in parts)
    except (TypeError, ValueError):
        return None
    return rgb if len(rgb) == 3 and all(0 <= c <= 255 for c in rgb) else None


class Light:
    def __init__(self, row):
        self.floor, self.area, self.id, self.name, self.state, self.brightness, self.rgb, modes = row
        self.color_capable = bool(set(modes or []) & COLOR_MODES)

    @property
    def on(self):
        return self.state == "on"

    def describe(self) -> str:
        bits = [self.name]
        if self.brightness is not None:
            bits.append(f"{round(self.brightness * 100 / 255)}%")
        if self.rgb:
            bits.append("rgb(%d,%d,%d)" % tuple(int(c) for c in self.rgb))
        return " ".join(bits)


class House:
    def __init__(self, gateway):
        self.gw = gateway

    # who may use it ------------------------------------------------------------------------
    def backend_for(self, identity):
        """The Home Assistant client for this caller's house tools, or None (then they are not offered)."""
        cfg = self.gw.dir.settings.get("house") or {}
        if identity.kind == "household" or not identity.person:
            return None
        ha = cfg.get("ha")
        if ha:
            if identity.name not in (cfg.get("people") or []):
                return None
            url = self.gw.env.get(f"HA_{ha}_URL") or self.gw.env.get("GATEWAY_HA_URL") or ""
            token = self.gw.env.get(f"HA_{ha}_ADMIN_API_TOKEN") or ""
            if url and token and token not in ("set-in-keychain", "EDIT-ME", "changeme"):
                return self.gw.ha_factory(url, token)
        return None

    def tools(self) -> list[dict]:
        return [{**t, "name": f"{ALIAS}{SEP}{t['name']}"} for t in TOOLS]

    # reading ------------------------------------------------------------------------------
    def snapshot(self, ha) -> list[Light]:
        try:
            rows = json.loads(ha.template(SNAPSHOT_TEMPLATE))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"unexpected answer from Home Assistant ({exc})") from None
        return [Light(r) for r in rows]

    @staticmethod
    def names(lights) -> str:
        floors = {}
        for l in lights:
            floors.setdefault(l.floor, {}).setdefault(l.area, []).append(l)
        return "; ".join(f"{f} ({', '.join(f'{a} {sum(x.on for x in ls)}/{len(ls)}' for a, ls in areas.items())})"
                         for f, areas in floors.items())

    @staticmethod
    def match(lights, where: str):
        """Lights for 'floor 2', 'L2 Kitchen', 'Kata', a comma list of those, or 'all'. Loose on
        purpose: a floor named by a number matches areas labelled L<number>. ([], unmatched words)."""
        words = [_norm(w) for w in re.split(r"[;,]", where or "") if _norm(w)]
        if not words or any(w in ("all", "everywhere", "house", "whole house", "everything") for w in words):
            return list(lights), []
        picked, unmatched = [], []
        for w in words:
            hit = []
            m = re.fullmatch(r"(?:floor|level|l)\s*(\d+)(?:st|nd|rd|th)?", w) or re.fullmatch(r"(\d+)(?:st|nd|rd|th)? floor", w)
            for l in lights:
                f, a = _norm(l.floor), _norm(l.area)
                if m and (re.search(rf"\bl{m.group(1)}\b", a) or re.search(rf"\bl{m.group(1)}\b", f)):
                    hit.append(l)
                elif not m and (w == f or w == a or w in a or w in f):
                    hit.append(l)
            if hit:
                picked += [l for l in hit if l not in picked]
            else:
                unmatched.append(w)
        return picked, unmatched

    # the two tools ---------------------------------------------------------------------------
    def house_state(self, ha, args: dict) -> dict:
        lights = self.snapshot(ha)
        if not lights:
            return _text("No lights are assigned to any floor or area in Home Assistant.", True)
        where = (args or {}).get("where")
        scope, unmatched = self.match(lights, where) if where else (lights, [])
        if where and not scope:
            return _text(f"No floor or area matches {where!r}. Floors and areas (lights on/total): {self.names(lights)}.", True)
        on = [l for l in scope if l.on]
        lines = [time.strftime("Now: %a %d %b %Y %H:%M."),
                 f"Floors and areas (lights on/total): {self.names(scope)}.",
                 f"Lights on: {len(on)}." + ("" if on else " None.")]
        by_area = {}
        for l in on[:MAX_LIGHTS_SHOWN]:
            by_area.setdefault((l.floor, l.area), []).append(l.describe())
        lines += [f"- {f} / {a}: " + "; ".join(ds) for (f, a), ds in by_area.items()]
        if len(on) > MAX_LIGHTS_SHOWN:
            lines.append(f"(and {len(on) - MAX_LIGHTS_SHOWN} more)")
        if unmatched:
            lines.append(f"No match for: {', '.join(unmatched)}.")
        return _text("\n".join(lines))

    def lights_set(self, ha, args: dict) -> dict:
        args = args or {}
        where = args.get("where")
        if not where:
            return _text("Say where: a floor or area name, or 'all'.", True)
        state = args.get("state", "on")
        which = args.get("which", "on" if state == "on" else "all")
        if state not in ("on", "off") or which not in ("on", "all"):
            return _text("state is 'on' or 'off'; which is 'on' or 'all'.", True)
        bright = args.get("brightness_pct")
        if bright is not None:
            try:
                bright = max(1, min(100, int(bright)))
            except (TypeError, ValueError):
                return _text("brightness_pct is a number from 1 to 100.", True)
        raw = args.get("colors") or []
        raw = [raw] if isinstance(raw, str) else list(raw)[:MAX_COLORS]
        colors = [parse_color(c) for c in raw]
        if any(c is None for c in colors):
            bad = [str(r) for r, c in zip(raw, colors) if c is None]
            return _text(f"Not colors: {', '.join(bad)}. Use hex like '#ff71ce' or 'r,g,b' with each 0 to 255.", True)

        lights = self.snapshot(ha)
        scope, unmatched = self.match(lights, where)
        if not scope:
            return _text(f"No floor or area matches {where!r}. Floors and areas (lights on/total): {self.names(lights)}.", True)
        usable = [l for l in scope if l.state != "unavailable"]
        targets = [l for l in usable if l.on] if which == "on" and state == "on" else usable
        if not targets:
            return _text(f"No lights are on in {where}; {len(usable)} are off. Use which='all' to turn them on.", True)

        done, failed, i = [], [], 0
        for l in targets:
            data = {}
            service = "turn_off" if state == "off" else "turn_on"
            if state == "on":
                if bright:
                    data["brightness_pct"] = bright
                if colors and l.color_capable:
                    data["rgb_color"] = list(colors[i % len(colors)])
                    i += 1
            try:
                ha.call_service("light", service, l.id, data)
                done.append((l, data, ""))
            except Exception as exc:
                failed.append((l, data, str(exc)))
        verb = "off" if state == "off" else "set"
        parts = [f"{len(done)} light(s) {verb} in {where}" + (f" at {bright}%" if bright and state == "on" else "") + "."]
        if colors and state == "on":
            parts.append(", ".join(f"{l.name} rgb({','.join(str(c) for c in d['rgb_color'])})" for l, d, _ in done if "rgb_color" in d) + ".")
        if failed:
            parts.append(f"{len(failed)} failed: " + "; ".join(f"{l.name}: {t[:80]}" for l, _, t in failed[:3]) + ".")
        if unmatched:
            parts.append(f"No match for: {', '.join(unmatched)}.")
        return _text(" ".join(p for p in parts if p.strip(". ")), error=not done)

    def call(self, ha, tool: str, args: dict) -> tuple[dict, str]:
        """(result, kind) for one house tool; kind is what the audit records."""
        if tool == "house_state":
            return self.house_state(ha, args), "read"
        if tool == "lights_set":
            return self.lights_set(ha, args), "modify"
        return _text(f"Unknown tool 'house{SEP}{tool}'.", True), "read"
