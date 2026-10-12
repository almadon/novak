"""HTTP surface. Adapters and clients use /v1 with a bearer token; a person
approving a task from a notification uses /review/<token>, where the
unguessable token is the credential (the port is tailnet-only)."""
import hashlib
import hmac
import html
import json
import re
import shutil
import tempfile
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .sinks import build_sinks

SAFE_EXT = re.compile(r"^\.[a-z0-9]{1,5}$")


def parse_when(value: str | None) -> int:
    if not value:
        return int(time.time())
    try:
        return int(float(value))
    except ValueError:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp())


def ingest_file(settings, store, src: Path, source: str, recorded_at: int, filename: str):
    """Hash, keep one copy, and queue it. A repeat of the same audio is not queued twice."""
    digest = hashlib.sha256()
    with src.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    sha = digest.hexdigest()
    ext = Path(filename).suffix.lower()
    ext = ext if SAFE_EXT.match(ext) else ".bin"
    rec, created = store.add_recording(sha, source, recorded_at, filename[:200])
    if created:
        audio = settings.data / "audio"
        audio.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, audio / f"{sha}{ext}")
    return rec, created


def decide_proposal(settings, store, proposal, action: str):
    """Returns (http_status, message)."""
    if proposal["status"] != "pending":
        return 409, f"already {proposal['status']}"
    if action == "reject":
        store.decide(proposal["id"], "rejected")
        return 200, "rejected"
    sinks, problems = build_sinks(settings.cfg["sinks"])
    results = []
    for sink in (s for s in sinks if s.kind == "task"):
        try:
            results.append(f"{sink.name}: {sink.send({'title': proposal['title'], 'detail': proposal['detail'], 'due': proposal['due'] or '', 'recording_id': proposal['recording_id']})}")
        except Exception as exc:
            return 502, f"{sink.name} failed, still pending: {exc}"
    store.decide(proposal["id"], "approved",
                 "; ".join(results) or "approved; no task sink is configured")
    return 200, "approved"


def make_server(settings, store, host="0.0.0.0", port=8000):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet; the worker logs what matters
            pass

        # helpers ------------------------------------------------------------
        def _send(self, code, body, ctype="application/json"):
            payload = body if isinstance(body, bytes) else (
                body.encode() if isinstance(body, str) else json.dumps(body).encode())
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _authed(self) -> bool:
            sent = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return bool(settings.token) and hmac.compare_digest(sent, settings.token)

        def _page(self, token: str, note: str = ""):
            prop = store.proposal_by_token(token)
            if not prop:
                return self._send(404, "Not found", "text/plain")
            rec = store.recording(prop["recording_id"])
            rows = []
            for p in store._all("SELECT * FROM proposals WHERE recording_id=? ORDER BY id",
                                (prop["recording_id"],)):
                if p["status"] == "pending":
                    act = "".join(
                        f'<form method="post" action="/review/{token}/{p["id"]}/{a}">'
                        f'<button>{a.title()}</button></form>' for a in ("approve", "reject"))
                else:
                    act = f"<em>{html.escape(p['status'])}</em>"
                due = f" (due {html.escape(p['due'])})" if p["due"] else ""
                rows.append(f"<li><strong>{html.escape(p['title'])}</strong>{due}<br>"
                            f"<small>{html.escape(p['detail'])}</small><div>{act}</div></li>")
            page = (
                "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                "<title>Review tasks</title><style>body{font:16px system-ui;margin:1rem auto;max-width:34rem;padding:0 1rem}"
                "li{margin:1rem 0}form{display:inline}button{font-size:1rem;padding:.4rem 1rem;margin:.3rem .5rem 0 0}</style>"
                f"<h1>{html.escape(rec['title'] or 'Recording')}</h1>"
                + (f"<p>{html.escape(note)}</p>" if note else "")
                + f"<ul>{''.join(rows)}</ul>")
            self._send(200, page, "text/html; charset=utf-8")

        # routes -------------------------------------------------------------
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/healthz":
                return self._send(200, {"ok": True})
            if m := re.fullmatch(r"/review/([\w-]+)", path):
                return self._page(m.group(1))
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            if path == "/v1/recordings":
                return self._send(200, store.recordings())
            if m := re.fullmatch(r"/v1/recordings/(\d+)", path):
                rec = store.recording(int(m.group(1)))
                return self._send(200 if rec else 404, rec or {"error": "not found"})
            if path == "/v1/proposals":
                q = self.path.partition("?")[2]
                status = q.split("status=", 1)[1].split("&")[0] if "status=" in q else "pending"
                return self._send(200, store.proposals(status))
            self._send(404, {"error": "not found"})

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            if m := re.fullmatch(r"/review/([\w-]+)/(\d+)/(approve|reject)", path):
                prop = store.proposal(int(m.group(2)))
                tok = store.proposal_by_token(m.group(1))
                if not prop or not tok or prop["recording_id"] != tok["recording_id"]:
                    return self._send(404, "Not found", "text/plain")
                code, msg = decide_proposal(settings, store, prop, m.group(3))
                return self._page(m.group(1), msg) if code == 200 else self._send(code, msg, "text/plain")
            if not self._authed():
                return self._send(401, {"error": "unauthorized"})
            if path == "/v1/recordings":
                return self._upload()
            if m := re.fullmatch(r"/v1/proposals/(\d+)/(approve|reject)", path):
                prop = store.proposal(int(m.group(1)))
                if not prop:
                    return self._send(404, {"error": "not found"})
                code, msg = decide_proposal(settings, store, prop, m.group(2))
                return self._send(code, {"result": msg})
            self._send(404, {"error": "not found"})

        def _upload(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > settings.max_upload_mb * 1024 * 1024:
                # Drain a bounded amount first: replying and closing with unread
                # data makes the client see a connection reset, not the 413.
                left = min(length, 64 * 1024 * 1024)
                while left > 0:
                    got = self.rfile.read(min(1 << 20, left))
                    if not got:
                        break
                    left -= len(got)
                return self._send(413 if length else 400, {"error": "bad or oversize body"})
            try:
                recorded = parse_when(self.headers.get("X-Recorded-At"))
            except ValueError:
                return self._send(400, {"error": "X-Recorded-At must be unix seconds or ISO 8601"})
            with tempfile.NamedTemporaryFile(dir=settings.data, delete=True) as tmp:
                left = length
                while left:
                    block = self.rfile.read(min(1 << 20, left))
                    if not block:
                        return self._send(400, {"error": "body shorter than Content-Length"})
                    tmp.write(block)
                    left -= len(block)
                tmp.flush()
                rec, created = ingest_file(
                    settings, store, Path(tmp.name), self.headers.get("X-Source", "unknown")[:60],
                    recorded, self.headers.get("X-Filename", "recording.bin"))
            self._send(201 if created else 200, {"id": rec["id"], "duplicate": not created})

    return ThreadingHTTPServer((host, port), Handler)
