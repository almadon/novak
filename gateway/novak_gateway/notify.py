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
        data = {"url": url, "clickAction": url, "tag": f"novak-{token[:16]}",
                "actions": [{"action": f"NOVAK_APPROVE_{token}", "title": "Approve"},
                            {"action": f"NOVAK_DENY_{token}", "title": "Deny", "destructive": True},
                            {"action": "URI", "title": "Review", "uri": url}]}
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
    return f"unknown notification kind {kind!r}"
