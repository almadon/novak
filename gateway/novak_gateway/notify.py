"""Tell a person something is waiting for them. Their own channel first:
Ticker category per person, or a Home Assistant notify service per person."""
import json
import urllib.error
import urllib.request


def _post(ha_url, token, path, body, timeout=15):
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
    except urllib.error.HTTPError as exc:
        # Home Assistant says why in the body (an unknown Ticker category, say).
        raise RuntimeError(f"Home Assistant refused ({exc.code}): {exc.read().decode()[:200]}") from exc


def describe(entry: str, tool: str, args: dict | None) -> str:
    """One short line saying what is being asked, for a person deciding on their phone."""
    a = args or {}
    if a.get("domain") and a.get("service"):
        what = f"{a['domain']}.{a['service']} {a.get('entity_id') or ''}".strip()
    else:
        what = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(a.items())[:4])
    return f"{entry}: {tool} {what}".strip()


def pending_value(token: str, person: str, text: str) -> str:
    """What the approvals page reads: a JSON object kept under Home Assistant's 255-character
    limit for an input_text, trimming the description rather than the token."""
    base = {"t": token, "who": person, "do": ""}
    room = 255 - len(json.dumps(base, separators=(",", ":"))) - 2
    base["do"] = text[:max(room, 0)]
    return json.dumps(base, separators=(",", ":"))


def read_state(ha_url, token, entity, timeout=10) -> str:
    """The state of one Home Assistant entity (the approval helper), or ''."""
    req = urllib.request.Request(f"{ha_url.rstrip('/')}/api/states/{entity}",
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return str(json.load(r).get("state", ""))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return ""
        raise


def expand(cfg: dict, groups: dict | None) -> dict:
    """A `kind: ha` channel may name a group from gateway.yaml's notify_groups
    (a list of notify services, for example both phones); returns a copy whose
    `service` is a list."""
    cfg = dict(cfg or {})
    if cfg.get("kind") == "ha":
        svc = cfg.get("service") or []
        names = svc if isinstance(svc, list) else [svc]
        out = []
        for n in names:
            n = str(n).removeprefix("notify.")
            out.extend((groups or {}).get(n) or [n])
        cfg["service"] = [str(n).removeprefix("notify.") for n in out]
    return cfg


def send(person_notify: dict, default: dict, ha_url: str, ha_token: str,
         title: str, message: str, url: str, post=_post) -> str:
    """Returns a short description of what was done, or why nothing was."""
    cfg = person_notify or default or {}
    kind = cfg.get("kind")
    if not (ha_url and ha_token and kind):
        return "no notification channel configured"
    if kind == "ticker":
        post(ha_url, ha_token, "/api/services/ticker/notify",
             {"category": cfg.get("category", "general"), "title": title, "message": message,
              "data": {"url": url, "clickAction": url}})
        return f"ticker:{cfg.get('category', 'general')}"
    if kind == "ha":
        token = url.rstrip("/").rsplit("/", 1)[-1]
        services = cfg["service"] if isinstance(cfg["service"], list) else [cfg["service"]]
        # Real buttons: a press fires mobile_app_notification_action in Home Assistant,
        # whose automation writes the action id into the approval helper, and the gateway
        # reads that (service.py). The link stays as a fallback.
        data = {"tag": f"novak-{token[:16]}",
                "actions": [{"action": f"NOVAK_APPROVE_{token}", "title": "Approve"},
                            {"action": f"NOVAK_DENY_{token}", "title": "Deny", "destructive": True}]}
        if cfg.get("page"):
            # A path inside Home Assistant opens in the app (an external address opens a browser).
            data["clickAction"] = cfg["page"]
        if cfg.get("link", True):
            # The review page is on the tailnet, so it only works there. With the helper
            # configured (link: false) the notification carries no link at all, and a tap
            # on its body just opens the app.
            data.update({"url": url, "clickAction": url})
            data["actions"].append({"action": "URI", "title": "Review", "uri": url})
        sent, errors = [], []
        for svc in services:
            svc = str(svc).removeprefix("notify.")
            try:
                post(ha_url, ha_token, f"/api/services/notify/{svc}", {"title": title, "message": message, "data": data})
                sent.append(svc)
            except Exception as exc:          # one phone being off must not hide the other
                errors.append(f"{svc}: {exc}")
        if not sent:
            raise RuntimeError("; ".join(errors) or "no notify service named")
        return "ha:" + ",".join(sent) + (f" (failed: {'; '.join(errors)})" if errors else "")
    if kind == "supernotify":
        # Supernotify (a Home Assistant integration) picks the person's phones from HA's own
        # people and carries the buttons through. Fields are top level in the call; the target is
        # a person entity (person.tyler_meuse) or several. Verified against a live install
        # (decision #72): actions, clickAction and tag reach the Companion app unchanged.
        token = url.rstrip("/").rsplit("/", 1)[-1]
        target = cfg.get("target") or []
        target = [target] if isinstance(target, str) else list(target)
        if not target:
            raise RuntimeError("supernotify channel needs a target (a person entity such as person.tyler_meuse)")
        mobile = {"tag": f"novak-{token[:16]}"}
        if cfg.get("page"):
            mobile["clickAction"] = cfg["page"]
        post(ha_url, ha_token, "/api/services/supernotify/notify",
             {"title": title, "message": message, "target": target, "priority": cfg.get("priority", "high"),
              "force_resend": True,              # a repeated request is a new request, not a duplicate
              "actions": [{"action": f"NOVAK_APPROVE_{token}", "title": "Approve"},
                          {"action": f"NOVAK_DENY_{token}", "title": "Deny"}],
              "delivery": {"mobile_push": {"data": mobile}}})
        return "supernotify:" + ",".join(target)
    return f"unknown notification kind {kind!r}"
