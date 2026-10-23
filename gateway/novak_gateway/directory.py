"""Who exists and what each person may reach.

Two files, both under the deployment's registry/ folder:
  people.yaml   the directory: people, their sign-in names, their entries
  gateway.yaml  behaviour: clients that may vouch for a user, policy, timeouts
The MCP registry (mcp-servers.yaml) says where each entry lives and which
variable holds its credential. Nothing here holds a secret, only hashes of
the keys people and clients present and the NAMES of credential variables.
"""
import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class ConfigError(ValueError):
    pass


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def key_matches(presented: str, stored_hash: str | None) -> bool:
    return bool(presented and stored_hash) and hmac.compare_digest(sha256(presented), stored_hash)


@dataclass
class Entry:
    name: str
    url: str
    token_env: str | None
    kind: str                      # external | container
    url_env: str | None = None     # the address is a secret, held in this variable
    user: str | None = None        # whose account the credential is, when the entry says

    @property
    def alias(self) -> str:        # tool-name prefix: hindsight-tmeuze -> hindsight_tmeuze
        return self.name.replace("-", "_")


@dataclass
class Person:
    name: str
    names: list[str]
    emails: list[str]
    entries: list[str]
    key_sha256: str | None = None
    notify: dict = field(default_factory=dict)


@dataclass
class Directory:
    people: dict[str, Person]
    household_entries: list[str]
    household_key_sha256: str | None
    entries: dict[str, Entry]
    settings: dict
    loaded_mtimes: tuple = ()

    def find_person(self, who: str) -> Person | None:
        who = who.strip().lower()
        for p in self.people.values():
            if who == p.name or who in (n.lower() for n in p.names) or who in (e.lower() for e in p.emails):
                return p
        return None

    def person_by_key(self, key: str) -> Person | None:
        return next((p for p in self.people.values() if key_matches(key, p.key_sha256)), None)

    def entries_for(self, person: Person | None) -> list[Entry]:
        names = person.entries if person else self.household_entries
        return [self.entries[n] for n in names if n in self.entries]


def tool_allowed(filters: list, entry_name: str, tool: str) -> bool:
    """Whether a model may be offered (and may call) this tool.

    `tool_filters` is a list of {entries: <glob>, allow: [globs], deny: [globs]},
    applied in order; the first filter whose `entries` glob matches the entry
    decides. With `allow`, only matching tools pass; `deny` then removes tools. A
    large tool list costs a small model its context and its judgement, so each
    kind of entry should offer the handful of tools people actually use.
    """
    import fnmatch
    for f in filters or []:
        if fnmatch.fnmatch(entry_name, f.get("entries", "*")):
            allow, deny = f.get("allow"), f.get("deny") or []
            if allow is not None and not any(fnmatch.fnmatch(tool, g) for g in allow):
                return False
            return not any(fnmatch.fnmatch(tool, g) for g in deny)
    return True


def _load_yaml(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def build_entries(registry: dict) -> dict[str, Entry]:
    out = {}
    for e in registry.get("servers") or []:
        if not e.get("enabled", False) or not e.get("name"):
            continue
        if e.get("kind") == "external":
            url, url_env = e.get("url") or "", e.get("url_env")
            if not (url or url_env) or "EDIT-ME" in url:
                continue
            out[e["name"]] = Entry(e["name"], url, e.get("auth"), "external", url_env, e.get("user"))
        else:  # a container the reconciler runs, reachable by service name
            out[e["name"]] = Entry(e["name"], f"http://{e['name']}-mcp:8000/mcp", None, "container", None, e.get("user"))
    return out


DEFAULT_SETTINGS = {
    "username_claim": "preferred_username",
    "confirm": ["destructive"],
    "confirm_timeout_s": 180,
    "tool_overrides": {},
    "arg_rules": {},
    "tool_filters": [],
    "clients": [],
    "oidc": {},
    "notify_default": {},
}


def load(registry_dir: Path) -> Directory:
    p = registry_dir
    people_raw = _load_yaml(p / "people.yaml")
    gw_raw = (_load_yaml(p / "gateway.yaml").get("gateway")) or {}
    reg_raw = _load_yaml(p / "mcp-servers.yaml")
    entries = build_entries(reg_raw)
    settings = {**DEFAULT_SETTINGS, **gw_raw}

    people = {}
    for name, raw in (people_raw.get("people") or {}).items():
        if not NAME_RE.match(name):
            raise ConfigError(f"person name {name!r}: use a-z, 0-9 and hyphens")
        raw = raw or {}
        people[name] = Person(
            name=name, names=[str(n) for n in raw.get("names") or [name]],
            emails=[str(e) for e in raw.get("emails") or []],
            entries=list(raw.get("entries") or []), key_sha256=raw.get("key_sha256"),
            notify=raw.get("notify") or {})
    seen = {}
    for person in people.values():
        for ident in [person.name, *person.names, *person.emails]:
            if seen.setdefault(ident.lower(), person.name) != person.name:
                raise ConfigError(f"'{ident}' belongs to both {seen[ident.lower()]} and {person.name}")
    hh = people_raw.get("household") or {}
    # Two people must never share an entry that is personal to one of them.
    return Directory(people=people, household_entries=list(hh.get("entries") or []),
                     household_key_sha256=hh.get("key_sha256"), entries=entries,
                     settings=settings, loaded_mtimes=mtimes(p))


def mtimes(registry_dir: Path) -> tuple:
    return tuple((registry_dir / f).stat().st_mtime if (registry_dir / f).exists() else 0
                 for f in ("people.yaml", "gateway.yaml", "mcp-servers.yaml"))


def validate(d: Directory) -> list[str]:
    """Problems worth reporting at startup and by `check`; not fatal."""
    problems = []
    for person in d.people.values():
        for n in person.entries:
            if n not in d.entries:
                problems.append(f"{person.name}: entry '{n}' is not an enabled entry in mcp-servers.yaml")
    for n in d.household_entries:
        if n not in d.entries:
            problems.append(f"household: entry '{n}' is not an enabled entry in mcp-servers.yaml")
    # An entry that says whose account it is must be listed for that person only: this
    # is what stops one person's token being attached to another by a slip of the pen.
    for person in d.people.values():
        for n in person.entries:
            entry = d.entries.get(n)
            if entry and entry.user and entry.user != person.name:
                problems.append(f"{person.name}: entry '{n}' is {entry.user}'s account, not {person.name}'s")
    for n in d.household_entries:
        entry = d.entries.get(n)
        if entry and entry.user:
            problems.append(f"household: entry '{n}' is {entry.user}'s own account and cannot be shared with the household")
    owners: dict[str, list[str]] = {}
    for person in d.people.values():
        for n in person.entries:
            owners.setdefault(n, []).append(person.name)
    for n, who in owners.items():
        if len(who) > 1:
            problems.append(f"entry '{n}' is listed for {', '.join(who)}: one credential, several people. "
                            "Give each person their own entry, or list it under household.")
        if n in d.household_entries:
            problems.append(f"entry '{n}' is both personal ({who[0]}) and household")
    return problems
