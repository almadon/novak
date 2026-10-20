"""A minimal MCP client for streamable-HTTP servers: initialize, list, call.

Just enough for the sinks. Servers may answer a POST with plain JSON or with a
one-event SSE stream; both are handled.
"""
import json
import urllib.request

PROTOCOL = "2025-03-26"


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, url: str, token: str | None = None, timeout: float = 30, headers: dict | None = None):
        self.url, self.token, self.timeout = url, token, timeout
        self.extra_headers = headers or {}
        self.session: str | None = None
        self._id = 0
        self._ready = False

    def _post(self, payload: dict, expect_reply: bool = True):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        headers.update(self.extra_headers)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode(), headers=headers
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session = sid
            raw = resp.read().decode()
            ctype = resp.headers.get("Content-Type", "")
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

    def _rpc(self, method: str, params: dict | None = None):
        self._id += 1
        msg = self._post(
            {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        )
        if msg is None or "error" in msg:
            raise MCPError(f"{method}: {(msg or {}).get('error', 'empty reply')}")
        return msg["result"]

    def _ensure_ready(self):
        if self._ready:
            return
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "novak-ingest", "version": "1"},
            },
        )
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, False)
        self._ready = True

    def list_tools(self) -> list[dict]:
        self._ensure_ready()
        return self._rpc("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        self._ensure_ready()
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise MCPError(f"{name} failed: {json.dumps(result.get('content'))[:300]}")
        return result
