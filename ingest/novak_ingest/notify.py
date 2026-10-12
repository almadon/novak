"""Tell a person a task is waiting for approval. First channel: a Home
Assistant notify service. The console and PWA push use the same proposals API
later, so nothing here is the only way to approve."""
import json
import urllib.request


def ha_notify(ha_url: str, token: str, target: str, title: str, message: str,
              review_url: str, timeout=15):
    """`target` is a notify service name, e.g. mobile_app_pixel. The action opens
    the review page, which needs no HA round trip to approve."""
    body = {"title": title, "message": message,
            "data": {"url": review_url, "clickAction": review_url,
                     "actions": [{"action": "URI", "title": "Review", "uri": review_url}]}}
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}/api/services/notify/{target}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()
