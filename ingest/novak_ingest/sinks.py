"""Where results go. Sinks are declared in registry/ingest.yaml; each one calls
an MCP tool with arguments built from a template.

Placeholders in string values, written {name}, are replaced with the values
for that kind of sink. Replacement is literal (no format-spec evaluation), so a
transcript containing braces cannot break or steer a template.
"""
import os
import re

from .mcp import MCPClient

_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def render_args(template, values: dict):
    if isinstance(template, str):
        return _PLACEHOLDER.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)
    if isinstance(template, dict):
        return {k: render_args(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [render_args(v, values) for v in template]
    return template


class McpSink:
    """kind: note (a finished note), memory (text to remember), task (approved task)."""

    def __init__(self, spec: dict, env=os.environ):
        self.name, self.kind = spec["name"], spec["kind"]
        self.tool, self.args = spec["tool"], spec.get("args", {})
        mcp = spec["mcp"]
        url = mcp.get("url") or env.get(mcp.get("url_env", ""), "")
        if not url:
            raise ValueError(f"sink {self.name}: no MCP url ({mcp.get('url_env')} unset)")
        token = env.get(mcp["token_env"]) if mcp.get("token_env") else None
        self.client = MCPClient(url, token)

    def send(self, values: dict) -> str:
        res = self.client.call_tool(self.tool, render_args(self.args, values))
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        return " ".join(texts)[:300]


class NoAccount(RuntimeError):
    """The owner has no account of the kind this sink needs (not an outage)."""


class Gateway:
    """Talks to the Novak gateway as one person at a time.

    Ingest holds a single trusted-client key and names the person a recording
    belongs to in a header, so the gateway applies that person's tools, filters
    and credentials and logs the call as theirs. Ingest keeps no service secrets.
    """

    TTL_S = 60

    def __init__(self, url: str, key: str, user_header: str = "X-Novak-User", clock=None):
        import time
        self.url, self.key, self.header = url, key, user_header
        self.clock = clock or time.time
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, tuple[float, list[str]]] = {}

    def client(self, owner: str) -> MCPClient:
        if owner not in self._clients:
            self._clients[owner] = MCPClient(self.url, self.key, headers={self.header: owner})
        return self._clients[owner]

    def tool_names(self, owner: str) -> list[str]:
        cached = self._tools.get(owner)
        if cached and self.clock() - cached[0] < self.TTL_S:
            return cached[1]
        names = [t["name"] for t in self.client(owner).list_tools()]
        self._tools[owner] = (self.clock(), names)
        return names

    def resolve(self, owner: str, service: str, tool: str, entry: str | None = None) -> str:
        """The gateway's name for `tool` on one of the owner's `service` accounts."""
        suffix = f"__{tool}"
        want = (entry or "").replace("-", "_")
        found = [n for n in self.tool_names(owner)
                 if n.endswith(suffix) and n.startswith(f"{service}_")
                 and (not want or n[: -len(suffix)] == want)]
        if not found:
            raise NoAccount(f"{owner} has no {service} account offering {tool}")
        return found[0]


class GatewaySink:
    """A sink that names a service and a tool, not an endpoint: which account it
    reaches is whatever the recording's owner has. kind: note, memory or task."""

    def __init__(self, spec: dict, gateway: Gateway, owner: str, owner_vars: dict | None = None):
        self.name, self.kind = spec["name"], spec["kind"]
        self.service, self.tool = spec["service"], spec["tool"]
        self.entry, self.args = spec.get("entry"), spec.get("args", {})
        self.gateway, self.owner, self.vars = gateway, owner, owner_vars or {}

    def send(self, values: dict) -> str:
        name = self.gateway.resolve(self.owner, self.service, self.tool, self.entry)
        res = self.gateway.client(self.owner).call_tool(name, render_args(self.args, {**self.vars, **values}))
        texts = [c.get("text", "") for c in res.get("content", []) if c.get("type") == "text"]
        return " ".join(texts)[:300]


def build_sinks(specs: list[dict], env=os.environ, gateway: Gateway | None = None, owner: str = "",
                owner_vars: dict | None = None) -> tuple[list, list[str]]:
    """Enabled sinks that could be built, plus a note for each one that could not.
    A spec with `service` goes through the gateway as `owner`; one with an `mcp`
    block calls its endpoint directly, as before."""
    sinks, problems = [], []
    for spec in specs or []:
        if not spec.get("enabled", False):
            continue
        try:
            if spec.get("service"):
                if gateway is None:
                    raise ValueError("the gateway is not configured (INGEST_GATEWAY_KEY)")
                if not owner:
                    raise ValueError("the recording has no owner (set ingest.owners in registry/ingest.yaml)")
                sinks.append(GatewaySink(spec, gateway, owner, owner_vars))
            else:
                sinks.append(McpSink(spec, env))
        except Exception as exc:
            problems.append(f"{spec.get('name', '?')}: {exc}")
    return sinks, problems
