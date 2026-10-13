"""What kind of action a tool is, and which kinds need a person's confirmation.

Appending (create, add, retain, store) is allowed. Removing needs confirmation.
Classification is by tool name, because MCP servers do not declare it reliably;
a server may override per tool in registry/gateway.yaml.
"""
import re

DESTRUCTIVE = re.compile(
    r"(^|_)(delete|remove|clear|destroy|purge|erase|drop|truncate|revoke|archive|"
    r"invalidate|cancel|reset|wipe|trash|disable|empty)(_|$)")
READ = re.compile(r"(^|_)(list|get|read|fetch|search|find|recall|reflect|query|show|"
                  r"describe|count|status|view|browse|lookup)(_|$)")
APPEND = re.compile(r"(^|_)(create|add|new|append|retain|sync_retain|store|save|post|"
                    r"insert|upload|import|log|record|capture|comment)(_|$)")
MODIFY = re.compile(r"(^|_)(update|edit|move|rename|set|change|modify|replace|restore|"
                    r"complete|refresh|mark|toggle|assign|merge)(_|$)")


def classify(tool: str, overrides: dict | None = None) -> str:
    """read | append | modify | destructive. Unknown names are treated as modify,
    which is allowed and logged: only recognised removals are held."""
    if overrides and tool in overrides:
        return overrides[tool]
    name = tool.lower()
    if DESTRUCTIVE.search(name):
        return "destructive"
    if READ.search(name):
        return "read"
    if APPEND.search(name):
        return "append"
    if MODIFY.search(name):
        return "modify"
    return "modify"
