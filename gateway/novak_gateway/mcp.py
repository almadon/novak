"""Upstream MCP client (streamable HTTP) with session reuse and one retry."""
import json
import threading
import urllib.error
import urllib.request

PROTOCOL = "2025-03-26"


class MCPError(RuntimeError):
    pass


class Upstream:
    def __init__(self, url: str, token: str | None = None, timeout: float = 60):
        self.url, self.token, self.timeout = url, token, timeout
        self.session: str | None = None
        self._id = 0
        self._ready = False
        self._lock = threading.Lock()

    def _post(self, payload: dict, expect_reply=True):
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session = sid
            raw, ctype = resp.read().decode(), resp.headers.get("Content-Type", "")
        if not expect_reply or not raw.strip():
            return None
        if "text/event-stream" in ctype:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    msg = json.loads(line[5:].strip())
                    if msg.get("id") == payload.get("id"):
                        return msg
            raise MCPError("no reply in event stream")
        return json.loads(raw)

    def _rpc(self, method, params=None):
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": method,
                          "params": params or {}})
        if msg is None or "error" in msg:
            raise MCPError(f"{method}: {(msg or {}).get('error', 'empty reply')}")
        return msg["result"]

    def _init(self):
        self.session = None
        self._rpc("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                 "clientInfo": {"name": "novak-gateway", "version": "1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, False)
        self._ready = True

    def call(self, method, params=None):
        """One upstream request. A stale session (restart, expiry) re-initialises once."""
        with self._lock:
            for attempt in (0, 1):
                try:
                    if not self._ready:
                        self._init()
                    return self._rpc(method, params)
                except (urllib.error.HTTPError, MCPError):
                    self._ready = False
                    if attempt:
                        raise
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    self._ready = False
                    if attempt:
                        raise MCPError(f"{method}: backend unreachable ({exc})") from exc
