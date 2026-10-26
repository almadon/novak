"""The gateway's logic, independent of HTTP: what a caller sees and may do."""
import fnmatch
import json
import os
import re
import threading
import time
from pathlib import Path

from . import directory, notify as notify_mod
from .house import ALIAS as HOUSE_ALIAS, House
from .tasks import ALIAS as TASKS_ALIAS, Tasks
from .homeassistant import HAClient
from .mcp import MCPError, Upstream
from .policy import classify, relaxed

SEP = "__"
TOOLS_TTL_S = 60
PROTOCOL = "2025-03-26"


def text_result(message: str, error=False) -> dict:
    return {"content": [{"type": "text", "text": message}], "isError": error}


class Gateway:
    def __init__(self, registry_dir, audit, approvals, public_url, env=os.environ,
                 notifier=notify_mod.send, upstream_factory=Upstream, clock=time.time,
                 helper_reader=notify_mod.read_state, helper_poll_s=1.5, publisher=notify_mod._post,
                 ha_factory=HAClient):
        self.registry_dir = Path(registry_dir)
        self.audit, self.approvals = audit, approvals
        self.public_url, self.env, self.notifier = public_url.rstrip("/"), env, notifier
        self.upstream_factory, self.clock = upstream_factory, clock
        self.helper_reader, self.helper_poll_s, self.publisher = helper_reader, helper_poll_s, publisher
        self._dir = directory.load(self.registry_dir)
        self._upstreams: dict[str, Upstream] = {}
        self._tools: dict[str, tuple[float, list]] = {}
        self.ha_factory = ha_factory
        self.house = House(self)
        self.tasks = Tasks(self)

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
        url = entry.url
        if entry.url_env:
            url = self.env.get(entry.url_env, "")
            if not url or url in ("set-in-keychain", "EDIT-ME", "changeme"):
                raise MCPError(f"the address of {entry.name} ({entry.url_env}) is not set")
        key = f"{entry.name}|{url}"
        if key not in self._upstreams:
            token = self.env.get(entry.token_env) if entry.token_env else None
            if entry.token_env and (not token or token in ("set-in-keychain", "EDIT-ME", "changeme")):
                raise MCPError(f"the credential for {entry.name} ({entry.token_env}) is not set")
            self._upstreams[key] = self.upstream_factory(url, token)
        return self._upstreams[key]

    # tools --------------------------------------------------------------------
    def _entry_tools(self, entry) -> list[dict]:
        cached = self._tools.get(entry.name)
        if cached and self.clock() - cached[0] < TOOLS_TTL_S:
            return cached[1]
        tools = self._upstream(entry).call("tools/list")["tools"]
        self._tools[entry.name] = (self.clock(), tools)
        return tools

    def _kind(self, entry, tool, args=None) -> str:
        kind = classify(tool, (self.dir.settings.get("tool_overrides") or {}).get(entry.name))
        rule = ((self.dir.settings.get("arg_rules") or {}).get(entry.name) or {}).get(tool)
        if kind == "destructive" and rule and relaxed(rule, args):
            return rule.get("to", "modify")
        return kind

    def list_tools(self, identity) -> list[dict]:
        out = []
        for entry in self._entries(identity):
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
        if self._house_entry(identity):
            out += self.house.tools()
        if self._tasks_entry(identity):
            out += self.tasks.tools()
        if identity.tools:
            out = [t for t in out if self._tool_wanted(identity, t["name"])]
        return out

    @staticmethod
    def _tool_wanted(identity, namespaced: str) -> bool:
        return not identity.tools or any(fnmatch.fnmatchcase(namespaced, g) for g in identity.tools)

    def _house_entry(self, identity):
        """Where the lean house tools run for this caller, if they may use them (the config names them
        and the connection's scope has not narrowed `house` away)."""
        entry = self.house.backend_for(identity)
        if entry and identity.scope and not any(fnmatch.fnmatchcase(HOUSE_ALIAS, g) for g in identity.scope):
            return None
        return entry

    def _tasks_entry(self, identity):
        """The person's Tududi entry for the lean tasks snapshot, unless the scope has narrowed it away."""
        entry = self.tasks.entry_for(identity)
        if entry and identity.scope and not any(fnmatch.fnmatchcase(g, TASKS_ALIAS) or fnmatch.fnmatchcase(entry.name, g) for g in identity.scope):
            return None
        return entry

    def _entries(self, identity):
        """What this caller may use, narrowed to the connection's scope when it names one."""
        entries = self.dir.entries_for(identity.person)
        if identity.scope:
            entries = [e for e in entries if any(fnmatch.fnmatchcase(e.name, g) for g in identity.scope)]
        return entries

    def _resolve(self, identity, namespaced: str):
        alias, _, tool = namespaced.partition(SEP)
        for entry in self._entries(identity):
            if entry.alias == alias and tool:
                return entry, tool
        return None, None

    def _call_house(self, identity, namespaced: str, args: dict) -> dict:
        t0 = self.clock()
        entry = self._house_entry(identity)
        tool = namespaced.partition(SEP)[2]
        if not entry or not self._tool_wanted(identity, namespaced):
            self.audit.record(identity, None, namespaced, None, "denied", "not one of this caller's tools", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        try:
            result, kind = self.house.call(entry, tool, args or {})
            outcome = "error" if result.get("isError") else "ok"
        except Exception as exc:
            result, kind, outcome = text_result(f"The house tools could not reach Home Assistant: {exc}", True), "read", f"error: {exc}"
        self.audit.record(identity, HOUSE_ALIAS, tool, kind, "allowed", outcome, (self.clock() - t0) * 1000, args)
        return result

    def _call_tasks(self, identity, namespaced: str, args: dict) -> dict:
        t0 = self.clock()
        entry = self._tasks_entry(identity)
        tool = namespaced.partition(SEP)[2]
        if not entry or not self._tool_wanted(identity, namespaced):
            self.audit.record(identity, None, namespaced, None, "denied", "not one of this caller's tools", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        try:
            result, kind = self.tasks.call(entry, tool, args or {})
            outcome = "error" if result.get("isError") else "ok"
        except Exception as exc:
            result, kind, outcome = text_result(f"The tasks snapshot could not reach Tududi: {exc}", True), "read", f"error: {exc}"
        self.audit.record(identity, TASKS_ALIAS, tool, kind, "allowed", outcome, (self.clock() - t0) * 1000, args)
        return result

    def call_tool(self, identity, namespaced: str, args: dict) -> dict:
        t0 = self.clock()
        if namespaced.startswith(TASKS_ALIAS + SEP):
            return self._call_tasks(identity, namespaced, args)
        if namespaced.startswith(HOUSE_ALIAS + SEP):
            return self._call_house(identity, namespaced, args)
        entry, tool = self._resolve(identity, namespaced)
        if not entry or not self._tool_wanted(identity, namespaced):
            self.audit.record(identity, None, namespaced, None, "denied", "not one of this caller's tools", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        if not directory.tool_allowed(self.dir.settings.get("tool_filters"), entry.name, tool):
            self.audit.record(identity, entry.name, tool, None, "denied", "not offered", args=args)
            return text_result(f"Unknown tool '{namespaced}'.", True)
        kind = self._kind(entry, tool, args)
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
            groups = self.dir.settings.get("notify_groups") or {}
            buttons = bool(self.dir.settings.get("approval_helper"))
            page = self.dir.settings.get("approval_page") or ""

            def channel(cfg):
                cfg = notify_mod.expand(cfg, groups)
                if cfg.get("kind") == "ha":
                    return {**cfg, "link": not buttons, "page": page}
                if cfg.get("kind") == "supernotify":
                    return {**cfg, "page": page}              # Supernotify always carries buttons
                return cfg
            sent = self.notifier(channel(person.notify if person else {}),
                                 channel(self.dir.settings.get("notify_default") or {}),
                                 self.env.get("GATEWAY_HA_URL", ""), self.env.get("GATEWAY_HA_TOKEN", ""),
                                 f"Confirm: {tool.replace('_', ' ')}", f"{entry.name}: {tool}. Tap to review.", url)
        except Exception as exc:
            sent = f"notification failed: {exc}"
        self.audit.record(identity, entry.name, tool, "destructive", "held", sent)
        timeout = float(self.dir.settings.get("confirm_timeout_s", 180))
        helper = self.dir.settings.get("approval_helper")
        have_ha = bool(self.env.get("GATEWAY_HA_URL") and self.env.get("GATEWAY_HA_TOKEN"))
        if helper and have_ha:
            threading.Thread(target=self._watch_helper, args=(pending, helper, timeout), daemon=True).start()
        shown = self.dir.settings.get("pending_helper") if have_ha else ""
        if shown:
            self._show_pending(shown, pending, notify_mod.describe(entry.name, tool, args))
        try:
            return self.approvals.wait(pending["id"], timeout)
        finally:
            if shown:
                self._clear_pending(shown, pending)

    def _set_helper(self, entity, value):
        self.publisher(self.env["GATEWAY_HA_URL"], self.env["GATEWAY_HA_TOKEN"], "/api/services/input_text/set_value",
                       {"entity_id": entity, "value": value})

    def _show_pending(self, entity, pending, text):
        """What the approvals page in Home Assistant shows. Best effort: the notification
        buttons work without it."""
        try:
            self._set_helper(entity, notify_mod.pending_value(pending["token"], pending["person"], text))
        except Exception:
            pass

    def _clear_pending(self, entity, pending):
        try:
            current = self.helper_reader(self.env["GATEWAY_HA_URL"], self.env["GATEWAY_HA_TOKEN"], entity)
            if not current or pending["token"] in current:      # leave a newer request's text alone
                self._set_helper(entity, "")
        except Exception:
            pass

    def _watch_helper(self, pending, entity, timeout):
        """A button on the notification lands in a Home Assistant helper (an automation
        writes the action id there); read it until this approval is decided or expires.
        Only an action carrying THIS approval's token counts, and a decision is final."""
        deadline = self.clock() + timeout
        want = re.compile(r"NOVAK_(APPROVE|DENY)_(.+)")
        while self.clock() < deadline:
            time.sleep(self.helper_poll_s)
            current = self.approvals.get(pending["id"])
            if not current or current["status"] != "pending":
                return
            try:
                state = self.helper_reader(self.env["GATEWAY_HA_URL"], self.env["GATEWAY_HA_TOKEN"], entity)
            except Exception:
                continue
            m = want.fullmatch(state or "")
            if m and m.group(2) == pending["token"]:
                self.approvals.decide(pending["id"], m.group(1) == "APPROVE")
                return

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
