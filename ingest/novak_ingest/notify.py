"""Tell a person a task is waiting for approval. First channel: a Home
Assistant notify service. The console and PWA push use the same proposals API
later, so nothing here is the only way to approve."""
import json
import urllib.error
import urllib.parse
import urllib.request


def _post(ha_url, token, path, body, timeout):
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}{path}", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        r.read()


def apprise_notify(url: str, key: str, tag: str, title: str, body: str, kind: str = "info",
                   timeout=15, opener=urllib.request.urlopen):
    """A plain notice through Apprise (decision #70): POST <url>/notify/<key> with a tag, which
    Apprise maps to whatever channels that tag has. Fire-and-forget: no buttons, no callback
    (approvals stay on Home Assistant). `kind` is info, success, warning or failure. Raises on
    anything but a 2xx; the key is never in the message."""
    if kind not in ("info", "success", "warning", "failure"):
        raise ValueError(f"unknown notice type {kind!r}")
    form = urllib.parse.urlencode({"tag": tag, "title": title[:250], "body": body[:1800], "type": kind}).encode()
    req = urllib.request.Request(f"{url.rstrip('/')}/notify/{urllib.parse.quote(key, safe='')}", data=form, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with opener(req, timeout=timeout) as r:
            r.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Apprise refused the notice ({exc.code})") from None
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"cannot reach Apprise: {getattr(exc, 'reason', exc)}") from None


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
