"""A person's standing instructions, served as a tool named after them (decision #78).

One file per person, `profiles/<name>.md` in the registry directory (private, never in the repo), says who
the assistant should be for that person: how to talk, how to plan, what to hold them to. Every client reaches
it the same way, through the gateway, which already knows who is asking: the tool `<name>__profile`
(`tmeuze__profile`). The tool's description tells the model to read it once at the start of a conversation
and follow it, so no shared prompt has to name a per-person tool.

Offered only to the person it belongs to, and only when their file exists. Read at call time, so an edit
takes effect at once. Kept short on purpose: the local models have an 8,192-token window.
"""
import re
from pathlib import Path

SEP = "__"
TOOL = "profile"
MAX_CHARS = 4000
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _text(msg: str, error=False) -> dict:
    return {"content": [{"type": "text", "text": msg}], "isError": error}


class Profile:
    def __init__(self, gateway):
        self.gw = gateway

    def alias(self, identity):
        """The tool's alias (the person's username), or None when they have no profile file."""
        if identity.kind != "person" or not identity.person or not NAME_RE.match(identity.name or ""):
            return None
        return identity.name if self._path(identity).is_file() else None

    def _path(self, identity) -> Path:
        return self.gw.registry_dir / "profiles" / f"{identity.name}.md"

    def tools(self, identity) -> list[dict]:
        alias = self.alias(identity)
        if not alias:
            return []
        return [{"name": f"{alias}{SEP}{TOOL}",
                 "description": f"{alias}'s standing instructions for how you work with them. Call once at the start "
                                "of every conversation, then follow it for the whole conversation.",
                 "inputSchema": {"type": "object", "properties": {}}}]

    def call(self, identity) -> dict:
        text = self._path(identity).read_text(encoding="utf-8").strip()
        if len(text) > MAX_CHARS:
            text = text[:MAX_CHARS].rstrip() + "\n(Cut short: the profile is longer than the model can hold.)"
        return _text(text)
