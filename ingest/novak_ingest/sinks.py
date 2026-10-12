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


def build_sinks(specs: list[dict], env=os.environ) -> tuple[list[McpSink], list[str]]:
    """Enabled sinks that could be built, plus a note for each one that could not."""
    sinks, problems = [], []
    for spec in specs or []:
        if not spec.get("enabled", False):
            continue
        try:
            sinks.append(McpSink(spec, env))
        except Exception as exc:
            problems.append(f"{spec.get('name', '?')}: {exc}")
    return sinks, problems
