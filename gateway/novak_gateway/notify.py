"""Tell a person something is waiting for them. Their own channel first:
Ticker category per person, or a Home Assistant notify service per person."""
import json
import urllib.request


def _post(ha_url, token, path, body, timeout=15):
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


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
        service = cfg["service"].removeprefix("notify.")
        post(ha_url, ha_token, f"/api/services/notify/{service}",
             {"title": title, "message": message,
              "data": {"url": url, "clickAction": url,
                       "actions": [{"action": "URI", "title": "Review", "uri": url}]}})
        return f"ha:{service}"
    return f"unknown notification kind {kind!r}"
