"""HTTP surface: the MCP endpoints, the approval page, and OAuth discovery."""
import html
import json
import re
import time
from urllib.parse import parse_qs, urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import AuthError, authenticate
from .changes import ChangeError
from .directory import key_matches, validate


def make_server(gw, oidc, host="0.0.0.0", port=8000):
    public = gw.public_url

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json", headers=None):
            payload = body if isinstance(body, bytes) else (
                body.encode() if isinstance(body, str) else json.dumps(body).encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(payload)

        def _auth_failure(self, exc: AuthError):
            hdr = {}
            if exc.status == 401 and oidc:
                hdr["WWW-Authenticate"] = f'Bearer resource_metadata="{public}/.well-known/oauth-protected-resource"'
            self._send(exc.status, {"error": exc.message}, headers=hdr)

        # GET ------------------------------------------------------------------
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                return self._send(200, {"ok": True})
            if path == "/.well-known/oauth-protected-resource" and oidc:
                return self._send(200, {"resource": f"{public}/mcp",
                                        "authorization_servers": [oidc.issuer],
                                        "bearer_methods_supported": ["header"]})
            if path == "/admin/today":
                return self._admin_today()
            if m := re.fullmatch(r"/approve/([\w-]+)", path):
                return self._approval_page(m.group(1))
            if path.startswith("/mcp"):
                return self._send(405, {"error": "this endpoint takes POST"}, headers={"Allow": "POST"})
            self._send(404, {"error": "not found"})

        def _admin_today(self):
            """Read-only status for the console. Its own key (gateway.yaml admin.key_sha256), which opens
            this one path and nothing else: it cannot call a tool, read an argument or decide an approval."""
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not key_matches(token, (gw.dir.settings.get("admin") or {}).get("key_sha256")):
                return self._send(401, {"error": "admin key required"})
            q = parse_qs(urlsplit(self.path).query)
            person = (q.get("person") or [None])[0]
            if person is not None and person not in gw.dir.people:
                return self._send(404, {"error": "no such person"})
            lt = time.localtime()
            since = int(time.mktime(lt[:3] + (0, 0, 0) + lt[6:]))
            summary = gw.audit.summary(since, person)
            self._send(200, {
                "now": int(time.time()), "person": person,
                "gateway": {"people": len(gw.dir.people), "entries": len(gw.dir.entries),
                            "problems": [] if person else validate(gw.dir)},
                "approvals": gw.approvals.listing(person), "activity": summary},
                headers={"Cache-Control": "no-store"})

        def _admin_change(self):
            """The console asking for a change on a person's behalf. Held for that person's yes on their phone."""
            auth = self.headers.get("Authorization", "")
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not key_matches(token, (gw.dir.settings.get("admin") or {}).get("change_key_sha256")):
                return self._send(401, {"error": "change key required"})
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 8192:
                return self._send(400, {"error": "bad body"})
            try:
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._send(400, {"error": "not JSON"})
            try:
                gw.changes.request(str(body.get("person", "")), str(body.get("action", "")),
                                   {k: v for k, v in body.items() if k not in ("person", "action")})
            except ChangeError as exc:
                return self._send(exc.status, {"error": exc.message})
            self._send(202, {"status": "asked"})

        def _approval_page(self, token, note=""):
            a = gw.approvals.by_token(token)
            if not a:
                return self._send(404, "Not found", "text/plain")
            args = json.loads(a["args"] or "{}")
            shown = html.escape(json.dumps(args, indent=2)[:1500])
            buttons = ""
            if a["status"] == "pending":
                buttons = "".join(
                    f'<form method="post" action="/approve/{token}/{x}"><button>{x.title()}</button></form>'
                    for x in ("approve", "deny"))
            else:
                buttons = f"<p><em>{html.escape(a['status'])}</em></p>"
            page = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                    "<title>Confirm</title><style>body{font:16px system-ui;margin:1rem auto;max-width:34rem;padding:0 1rem}"
                    "pre{background:#8881;padding:.7rem;overflow:auto}form{display:inline}"
                    "button{font-size:1rem;padding:.5rem 1.2rem;margin:.4rem .6rem 0 0}</style>"
                    f"<h1>Confirm: {html.escape(a['tool'].replace('_', ' '))}</h1>"
                    f"<p>{html.escape(a['person'])} asked, through {html.escape(a['entry'])}.</p>"
                    + (f"<p>{html.escape(note)}</p>" if note else "")
                    + f"<pre>{shown}</pre>{buttons}")
            self._send(200, page, "text/html; charset=utf-8")

        # POST -----------------------------------------------------------------
        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if m := re.fullmatch(r"/approve/([\w-]+)/(approve|deny)", path):
                a = gw.approvals.by_token(m.group(1))
                if not a:
                    return self._send(404, "Not found", "text/plain")
                done = gw.approvals.decide(a["id"], m.group(2) == "approve")
                return self._approval_page(m.group(1), "Recorded." if done else f"Already {a['status']}.")
            if path == "/admin/changes":
                return self._admin_change()
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 4 * 1024 * 1024:
                return self._send(400, {"error": "bad body"})
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                return self._send(400, {"error": "not JSON"})
            hm = re.fullmatch(r"/mcp/household(?:/k/([\w-]+))?", path)   # key in the URL for clients that cannot send headers
            household = hm is not None
            km = re.fullmatch(r"/mcp/k/([\w-]+)", path)
            if not (path == "/mcp" or household or km):
                return self._send(404, {"error": "not found"})
            try:
                ident = authenticate(gw.dir, self.headers, oidc,
                                     km.group(1) if km else (hm.group(1) if hm else None), household)
            except AuthError as exc:
                return self._auth_failure(exc)
            msgs = body if isinstance(body, list) else [body]
            replies = [r for r in (gw.handle(ident, m) for m in msgs if isinstance(m, dict)) if r]
            if not replies:
                return self._send(202, b"", "application/json")
            self._send(200, replies if isinstance(body, list) else replies[0])

    return ThreadingHTTPServer((host, port), Handler)
