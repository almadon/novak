#!/usr/bin/env python3
"""Manage the gateway's directory: `novak person ...` and `novak gateway ...`.

  people.py add NAME [--names a,b] [--emails x,y] [--entries e1,e2]
                     [--bank] [--ticker CATEGORY | --ha-service SERVICE] [--yes]
  people.py list
  people.py key NAME              new gateway key for a person (shown once)
  people.py attach NAME ENTRY...  give a person registry entries
  people.py detach NAME ENTRY...
  people.py share ENTRY...        household entries (anyone, incl. satellites)
  people.py unshare ENTRY...
  people.py client NAME           trusted client (Open WebUI): new key, shown once
  people.py household-key         new household key, shown once

Edits registry/people.yaml and registry/gateway.yaml as text, so the comments
above each section survive; a person's own block is rewritten whole. Keys are
stored only as SHA-256 hashes. A key is printed once, to stderr, when it is made.
"""
import argparse
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import instances  # noqa: E402

NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))
PEOPLE = NOVAK_HOME / "registry" / "people.yaml"
GATEWAY = NOVAK_HOME / "registry" / "gateway.yaml"
REGISTRY = NOVAK_HOME / "registry" / "mcp-servers.yaml"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def say(msg=""):
    print(msg, file=sys.stderr)


def new_key() -> tuple[str, str]:
    key = secrets.token_urlsafe(32)
    return key, hashlib.sha256(key.encode()).hexdigest()


def load(path: Path) -> dict:
    return (yaml.safe_load(path.read_text()) or {}) if path.exists() else {}


def backup(path: Path):
    b = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(path, b)
    return b


def dump_block(key: str, value, indent: int) -> str:
    body = yaml.safe_dump({key: value}, sort_keys=False, default_flow_style=False, width=100)
    return "".join((" " * indent + l) if l.strip() else l for l in body.splitlines(True))


def block_range(lines: list[str], header: str, indent: int):
    """(start, end) of `header:` at `indent`, ending before the next key at or
    above that indent. Comments belong to whatever follows them."""
    pat = re.compile(rf"^{' ' * indent}{re.escape(header)}:(\s.*)?$")
    start = next((i for i, l in enumerate(lines) if pat.match(l.rstrip("\n"))), None)
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        ind = len(l) - len(l.lstrip())
        # A list under a key may sit at the key's own indent ("  clients:" then
        # "  - name: x"), which is still part of that key's block.
        if l.strip() and not l.lstrip().startswith("#") and ind <= indent \
                and not (ind == indent and l.lstrip().startswith("- ")):
            end = j
            break
    # leave trailing comments/blank lines that introduce the next section
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def write_block(path: Path, header: str, indent: int, value, append_ok=True):
    lines = path.read_text().splitlines(True)
    rng = block_range(lines, header, indent)
    text = dump_block(header, value, indent)
    if rng is None:
        if not append_ok:
            raise SystemExit(f"{header} not found in {path.name}")
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(text)
    else:
        lines[rng[0]:rng[1]] = [text]
    path.write_text("".join(lines))


def people_entries(d):
    return d.get("people") or {}


def owned_entries(d) -> dict[str, str]:
    owned = {e: "household" for e in (d.get("household") or {}).get("entries") or []}
    for n, p in people_entries(d).items():
        for e in (p or {}).get("entries") or []:
            owned[e] = n
    return owned


def registry_entries() -> list[str]:
    return [e["name"] for e in (load(REGISTRY).get("servers") or []) if e.get("name")]


def need_files():
    if not PEOPLE.exists():
        raise SystemExit(f"No {PEOPLE}: run 'novak up' once to seed it.")


# --- commands ---------------------------------------------------------------
def cmd_add(a):
    need_files()
    name = a.name
    if not NAME_RE.match(name):
        raise SystemExit(f"'{name}' is not a valid person name (a-z, 0-9, hyphens)")
    d = load(PEOPLE)
    if name in people_entries(d):
        raise SystemExit(f"{name} already exists")
    answers = dict(kv.split("=", 1) for kv in a.set or [])
    names = [n for n in (a.names or name).split(",") if n]
    emails = [e for e in (a.emails or "").split(",") if e]
    entries = [e for e in (a.entries or "").split(",") if e]
    notify = {}
    if a.ticker:
        notify = {"kind": "ticker", "category": a.ticker}
    elif a.ha_service:
        notify = {"kind": "ha", "service": a.ha_service}
    elif not a.yes:
        c = instances.ask(answers, "ticker", f"Ticker category for {name}'s confirmations (blank to skip)", "")
        notify = {"kind": "ticker", "category": c} if c else {}
    if not a.yes and not emails:
        emails = [e for e in instances.ask(answers, "emails", "Email(s) Open WebUI knows them by, comma separated (blank for none)", "").split(",") if e]

    if a.bank or (not a.yes and instances.yn(answers, "bank", f"Create a Hindsight memory bank '{name}'?", True)):
        cmd = [sys.executable, str(Path(instances.__file__)), "add", "--kind", "hindsight", "--name", name,
               "--set", "voice_safe=n", "--accepted-by", a.accepted_by or os.environ.get("USER", "admin"), "--yes"]
        r = subprocess.run(cmd, env={**os.environ, "NOVAK_HOME": str(NOVAK_HOME)})
        if r.returncode != 0:
            raise SystemExit("could not add the memory bank; person not created")
        entries.append(f"hindsight-{name}")

    free = [e for e in registry_entries() if e not in owned_entries(d) and e not in entries]
    if free and not a.yes and not a.entries:
        say(f"Entries nobody owns yet: {', '.join(free)}")
        more = instances.ask(answers, "attach", f"Entries that are {name}'s own (comma separated, blank for none)", "")
        entries += [e for e in more.split(",") if e]
    taken = [e for e in entries if e in owned_entries(d)]
    if taken:
        raise SystemExit(f"already owned: {', '.join(f'{e} ({owned_entries(d)[e]})' for e in taken)}")
    unknown = [e for e in entries if e not in registry_entries()]
    if unknown:
        raise SystemExit(f"not in the registry: {', '.join(unknown)} (add with `novak add`)")

    person = {"names": names, "emails": emails, "entries": entries}
    key = None
    if not a.no_key:
        key, person["key_sha256"] = new_key()
    if notify:
        person["notify"] = notify
    backup(PEOPLE)
    lines = PEOPLE.read_text()
    if not re.search(r"^people:\s*$", lines, re.M):
        raise SystemExit("people.yaml has no 'people:' section")
    write_block(PEOPLE, name, 2, person)
    say(f"Added {name}.")
    if key:
        say(f"\nGateway key for {name} (shown once, keep it somewhere safe):\n  {key}")
        say("Use it as a bearer token, or in a URL for clients that cannot send headers:")
        say(f"  <gateway>/mcp/k/{key}")
    print("KEY_MADE" if key else "NO_KEY")
    return 0


def cmd_list(a):
    need_files()
    d = load(PEOPLE)
    hh = d.get("household") or {}
    say(f"household   key {'set' if hh.get('key_sha256') else 'NOT SET'}   entries: {', '.join(hh.get('entries') or []) or '-'}")
    for n, p in people_entries(d).items():
        p = p or {}
        ch = p.get("notify") or {}
        chan = ch.get("category") or ch.get("service") or "none"
        say(f"{n:11} key {'set' if p.get('key_sha256') else 'none'}   notify {ch.get('kind', '-')}:{chan}   "
            f"entries: {', '.join(p.get('entries') or []) or '-'}")
    return 0


def person_or_die(d, name):
    p = people_entries(d).get(name)
    if p is None:
        raise SystemExit(f"no such person: {name}")
    return p


def cmd_key(a):
    need_files()
    d = load(PEOPLE)
    p = person_or_die(d, a.name)
    key, h = new_key()
    p["key_sha256"] = h
    backup(PEOPLE)
    write_block(PEOPLE, a.name, 2, p)
    say(f"New key for {a.name} (shown once). The old key stops working.\n  {key}")
    return 0


def cmd_attach(a, remove=False):
    need_files()
    d = load(PEOPLE)
    p = person_or_die(d, a.name)
    owned = owned_entries(d)
    for e in a.entries:
        if remove:
            if e not in (p.get("entries") or []):
                raise SystemExit(f"{a.name} does not have {e}")
            p["entries"].remove(e)
        else:
            if e not in registry_entries():
                raise SystemExit(f"not in the registry: {e}")
            if e in owned and owned[e] != a.name:
                raise SystemExit(f"{e} already belongs to {owned[e]}: one credential stands for one person")
            p.setdefault("entries", [])
            if e not in p["entries"]:
                p["entries"].append(e)
    backup(PEOPLE)
    write_block(PEOPLE, a.name, 2, p)
    say(f"{a.name}: {', '.join(p.get('entries') or []) or '-'}")
    return 0


def cmd_share(a, remove=False):
    need_files()
    d = load(PEOPLE)
    hh = d.get("household") or {}
    hh.setdefault("entries", [])
    owned = owned_entries(d)
    for e in a.entries:
        if remove:
            if e in hh["entries"]:
                hh["entries"].remove(e)
        else:
            if e not in registry_entries():
                raise SystemExit(f"not in the registry: {e}")
            if owned.get(e) not in (None, "household"):
                raise SystemExit(f"{e} belongs to {owned[e]}; a personal entry cannot be household")
            if e not in hh["entries"]:
                hh["entries"].append(e)
    backup(PEOPLE)
    write_block(PEOPLE, "household", 0, hh)
    say(f"household: {', '.join(hh['entries']) or '-'}")
    return 0


def cmd_household_key(a):
    need_files()
    d = load(PEOPLE)
    hh = d.get("household") or {"entries": []}
    key, hh["key_sha256"] = new_key()
    backup(PEOPLE)
    write_block(PEOPLE, "household", 0, hh)
    say(f"Household key (shown once). Satellites use <gateway>/mcp/household with it as a bearer token.\n  {key}")
    return 0


def cmd_client(a):
    if not GATEWAY.exists():
        raise SystemExit(f"No {GATEWAY}: run 'novak up' once to seed it.")
    d = (load(GATEWAY).get("gateway")) or {}
    clients = [c for c in d.get("clients") or [] if c.get("name") != a.name]
    key, h = new_key()
    clients.append({"name": a.name, "key_sha256": h, "user_header": "X-Novak-User"})
    lines = GATEWAY.read_text().splitlines(True)
    rng = block_range(lines, "clients", 2)
    if rng is None:
        raise SystemExit("gateway.yaml has no 'clients:' key")
    backup(GATEWAY)
    lines[rng[0]:rng[1]] = [dump_block("clients", clients, 2)]
    GATEWAY.write_text("".join(lines))
    say(f"Trusted client '{a.name}'. Its key (shown once):\n  {key}")
    say("The client sends it as 'Authorization: Bearer <key>' and names the user in the X-Novak-User header.")
    say("Nothing but that client should be able to reach the gateway.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("add")
    s.add_argument("name")
    s.add_argument("--names"); s.add_argument("--emails"); s.add_argument("--entries")
    s.add_argument("--bank", action="store_true")
    s.add_argument("--ticker"); s.add_argument("--ha-service")
    s.add_argument("--accepted-by"); s.add_argument("--no-key", action="store_true")
    s.add_argument("--set", action="append"); s.add_argument("--yes", action="store_true")
    sub.add_parser("list")
    k = sub.add_parser("key"); k.add_argument("name")
    for c in ("attach", "detach"):
        x = sub.add_parser(c); x.add_argument("name"); x.add_argument("entries", nargs="+")
    for c in ("share", "unshare"):
        x = sub.add_parser(c); x.add_argument("entries", nargs="+")
    c = sub.add_parser("client"); c.add_argument("name")
    sub.add_parser("household-key")
    a = ap.parse_args()
    return {"add": cmd_add, "list": cmd_list, "key": cmd_key, "attach": lambda a: cmd_attach(a),
            "detach": lambda a: cmd_attach(a, True), "share": lambda a: cmd_share(a),
            "unshare": lambda a: cmd_share(a, True), "client": cmd_client,
            "household-key": cmd_household_key}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
