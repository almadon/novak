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


def _domain(entity_id) -> str:
    return str(entity_id).split(".", 1)[0].strip().lower()


def relaxed(rule: dict | None, args: dict | None) -> bool:
    """Whether this call is one of the harmless kinds a rule names, so a tool that is
    held by default (a Home Assistant service call can unlock a door) lets it through.

    A rule is `{allow: {<domain>: [<service>, ...]}}`. It matches a call whose `domain`
    and `service` are both listed, or a bulk `operations` list whose every entity and
    action is. Anything that does not clearly match stays held: a missing domain, a
    target in another domain, a raw `ws_command`, an empty list."""
    args = args or {}
    allow = {str(d).lower(): [str(s).lower() for s in (v or [])] for d, v in ((rule or {}).get("allow") or {}).items()}
    if not allow or args.get("ws_command"):
        return False
    ops = args.get("operations")
    if ops:
        return all(isinstance(o, dict) and str(o.get("action", "")).lower() in allow.get(_domain(o.get("entity_id", "")), [])
                   for o in ops)
    domain, service = str(args.get("domain") or "").lower(), str(args.get("service") or "").lower()
    if service not in allow.get(domain, []):
        return False
    ids = [i for i in str(args.get("entity_id") or "").replace(" ", "").split(",") if i]
    return all(_domain(i) == domain for i in ids)


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
