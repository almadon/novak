"""The gateway's logic, independent of HTTP: what a caller sees and may do."""
import json
import os
import time
from pathlib import Path

from . import directory, notify as notify_mod
from .mcp import MCPError, Upstream
from .policy import classify

SEP = "__"
TOOLS_TTL_S = 60
PROTOCOL = "2025-03-26"


def text_result(message: str, error=False) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": error}


class Gateway:
    def __init__(self, registry_dir, audit, approvals, public_url, env=os.environ,
                 notifier=notify_mod.send, upstream_factory=Upstream, clock=time.time):
        self.registry_dir = Path(registry_dir)
        self.audit, self.approvals = audit, approvals
        self.public_url, self.env, self.notifier = public_url.rstrip("/"), env, notifier
        self.upstream_factory, self.clock = upstream_factory, clock
        self._dir = directory.load(self.registry_dir)
        self._upstreams: dict[str, Upstream] = {}
        self._tools: dict[str, tuple[float, list]] = {}

    # configuration ------------------------------------------------------------
    @property
    def dir(self) -> directory.Directory:
        if directory.mtimes(self.registry_dir) != self._dir.loaded_mtimes:
            try:
                self._dir = directory.load(self.registry_dir)
                self._upstreams.clear()
                self._tools.clear()
            except Exception:
                pass          # keep serving the last good configuration
        return self._dir

    def _upstream(self, entry) -> Upstream:
        key = f"{entry.name}|{entry.url}"
        if key not in self._upstreams:
            token = self.env.get(entry.token_env) if entry.token_env else None
            if entry.token_env and (not token or token in ("set-in-keychain", "EDIT-ME", "changeme")):
                raise MCPError(f"the credential for {entry.name} ({entry.token_env}) is not set")
            self._upstreams[key] = self.upstream_factory(entry.url, token)
        return self._upstreams[key]

    # tools --------------------------------------------------------------------
    def _entry_tools(self, entry) -> list[dict]:
        cached = self._tools.get(entry.name)
        if cached and self.clock() - cached[0] < TOOLS_TTL_S:
            return cached[1]
        tools = self._upstream(entry).call("tools/list")["tools"]
        self._tools[entry.name] = (self.clock(), tools)
        return tools

    def _kind(self, entry, tool) -> str:
        return classify(tool, (self.dir.settings.get("tool_overrides") or {}).get(entry.name))

    def list_tools(self, identity) -> list[dict]:
        out = []
        for entry in self.dir.entries_for(identity.person):
            try:
                tools = self._entry_tools(entry)
            except Exception as exc:
                self.audit.record(identity, entry.name, "tools/list", "read", "error", exc)
                continue          # one dead backend must not hide the others
            for t in tools:
                if not directory.tool_allowed(self.dir.settings.get("tool_filters"), entry.name, t["name"]):
                    continue
                kind = self._kind(entry, t["name"])
                if identity.kind == "household" and kind == "destructive":
                    continue      # nobody to confirm it: not offered at all
                out.append({**t, "name": f"{entry.alias}{SEP}{t['name']}",
                            "description": f"[{entry.name}] {t.get('description') or ''}".strip()})
        return out

    def _resolve(self, identity, namespaced: str):
        alias, _, tool = namespaced.partition(SEP)
        for entry in self.dir.entries_for(identity.person):
            if entry.alias == alias and tool:
                return entry, tool
        return None, None

    def call_tool(self, identity, namespaced: str, args: dict) -> dict:
        t0 = self.clock()
        entry, tool = self._resolve(identity, namespaced)
        if not entry:
            self.audit.record(identity, None, namespaced, None, "denied", "not one of this caller's tools", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        if not directory.tool_allowed(self.dir.settings.get("tool_filters"), entry.name, tool):
            self.audit.record(identity, entry.name, tool, None, "denied", "not offered", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        kind = self._kind(entry, tool)
        if kind in self.dir.settings.get("confirm", ["destructive"]):
            if identity.kind == "household":
                self.audit.record(identity, entry.name, tool, kind, "denied", "household cannot confirm", args=args)
                return text_result("This removes something and needs a signed-in person to confirm it.", True)
            verdict = self._confirm(identity, entry, tool, args)
            if verdict != "approved":
                self.audit.record(identity, entry.name, tool, kind, verdict, ms=(self.clock() - t0) * 1000, args=args)
                msg = {"denied": "The person declined, so nothing was changed.",
                       "expired": "No confirmation arrived in time, so nothing was changed. "
                                  "Ask them to confirm on their phone and try again."}[verdict]
                return text_result(msg, True)
            decision = "approved"
        else:
            decision = "allowed"
        try:
            result = self._upstream(entry).call("tools/call", {"name": tool, "arguments": args or {}})
            outcome = "error" if result.get("isError") else "ok"
        except Exception as exc:
            result, outcome = text_result(f"{entry.name} could not complete that: {exc}", True), f"error: {exc}"
        self.audit.record(identity, entry.name, tool, kind, decision, outcome,
                          (self.clock() - t0) * 1000, args)
        return result

    def _confirm(self, identity, entry, tool, args) -> str:
        pending = self.approvals.create(identity.name, entry.name, tool, args)
        url = f"{self.public_url}/approve/{pending['token']}"
        person = identity.person
        try:
            sent = self.notifier((person.notify if person else {}), self.dir.settings.get("notify_default") or {},
                                 self.env.get("GATEWAY_HA_URL", ""), self.env.get("GATEWAY_HA_TOKEN", ""),
                                 f"Confirm: {tool.replace('_', ' ')}", f"{entry.name}: {tool}. Tap to review.", url)
        except Exception as exc:
            sent = f"notification failed: {exc}"
        self.audit.record(identity, entry.name, tool, "destructive", "held", sent)
        return self.approvals.wait(pending["id"], float(self.dir.settings.get("confirm_timeout_s", 180)))

    # JSON-RPC -----------------------------------------------------------------
    def instructions(self, identity) -> str:
        who = "the household (shared, read and add only)" if identity.kind == "household" else identity.name
        return (f"You are acting for {who}. Tool names are prefixed with the service they belong to. "
                "Adding things is immediate. Anything that removes something is held until the person "
                "confirms it on their phone, so say you have asked and wait for the result.")

    def handle(self, identity, msg: dict):
        """One JSON-RPC message. Returns a response dict, or None for notifications."""
        method, mid = msg.get("method"), msg.get("id")
        if mid is None:
            return None
        def ok(result): return {"jsonrpc": "2.0", "id": mid, "result": result}
        def err(code, text): return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": text}}
        if method == "initialize":
            return ok({"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}},
                       "serverInfo": {"name": "novak-gateway", "version": "1"},
                       "instructions": self.instructions(identity)})
        if method == "ping":
            return ok({})
        if method == "tools/list":
            return ok({"tools": self.list_tools(identity)})
        if method == "tools/call":
            p = msg.get("params") or {}
            if not p.get("name"):
                return err(-32602, "tools/call needs a name")
            return ok(self.call_tool(identity, p["name"], p.get("arguments") or {}))
        if method in ("resources/list", "prompts/list"):
            return ok({method.split("/")[0]: []})
        return err(-32601, f"method not found: {method}")
