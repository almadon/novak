"""Serves Novak's voice persona to Home Assistant, which pulls it (decision #53).

The router injects the persona for Open WebUI, but HA's `litellm` agent
always sends its own system message, so injection is skipped for `ha-voice`
by design. HA used to hold a hand-pasted copy of prompts/novak-voice.md.
Instead, HA now polls this endpoint with a REST sensor and its Instructions
field is a template that reads the sensor, so prompts/ stays the only copy.

Read-only, stdlib only, no secrets: the persona is not sensitive, and the
route is exposed over Tailscale only (docker-compose.yml, PERSONA_BIND).
The file is re-read on every request, so an edit to prompts/ reaches HA at
its next poll with no restart, same promise as router/persona_hook.py.
"""
import hashlib
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PROMPTS_DIR = Path("/prompts")
ROUTES = {"/voice.json": "novak-voice.md"}


def load_persona(filename: str) -> str:
    """Same header-stripping rule as router/persona_hook.py's _load_persona."""
    text = (PROMPTS_DIR / filename).read_text()
    _, _, body = text.partition("\n---\n")
    return body.strip() or text.strip()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        filename = ROUTES.get(self.path.split("?", 1)[0])
        if filename is None:
            self.send_error(404)
            return
        try:
            body = load_persona(filename)
        except OSError as exc:
            print(f"cannot read {filename}: {exc}", file=sys.stderr)
            self.send_error(503, "persona file unreadable")
            return
        payload = json.dumps(
            {"text": body, "sha256": hashlib.sha256(body.encode()).hexdigest()}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
