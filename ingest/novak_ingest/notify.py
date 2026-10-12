"""Tell a person a task is waiting for approval. First channel: a Home
Assistant notify service. The console and PWA push use the same proposals API
later, so nothing here is the only way to approve."""
import json
import urllib.request


def _post(ha_url, token, path, body, timeout):
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def is_ticker(target: str) -> bool:
    return target.removeprefix("notify.") == "ticker"


def ticker_notify(ha_url: str, token: str, category: str, title: str, message: str,
                  review_url: str, timeout=15):
    """Ticker (HACS) routes by category to whoever subscribed. `notify.ticker` is
    a notify *entity*, and HA's notify.send_message passes only message and title,
    so the tap-to-open link needs Ticker's own `ticker.notify` action, whose
    `data` is passed on to the phone. `navigate_to` is no use: Ticker restricts it
    to a relative HA path, and this link goes to the ingest service. The category
    must exist in Ticker or the notification is skipped with a warning there."""
    _post(ha_url, token, "/api/services/ticker/notify",
          {"category": category, "title": title, "message": message,
           "data": {"url": review_url, "clickAction": review_url}}, timeout)


def ha_notify(ha_url: str, token: str, target: str, title: str, message: str,
              review_url: str, timeout=15):
    """`target` is a notify service name, e.g. mobile_app_pixel. The action opens
    the review page, which needs no HA round trip to approve."""
    body = {"title": title, "message": message,
            "data": {"url": review_url, "clickAction": review_url,
                     "actions": [{"action": "URI", "title": "Review", "uri": review_url}]}}
    _post(ha_url, token, f"/api/services/notify/{target}", body, timeout)
