#!/usr/bin/env python3
"""Manage the gateway's directory: `novak person ...` and `novak gateway ...`.

  people.py add NAME [--names a,b] [--emails x,y] [--entries e1,e2]
                     [--bank] [--ticker CATEGORY | --ha-service SERVICE] [--yes]
  people.py list
  people.py set NAME [--names a,b] [--emails x,y] [--ticker CATEGORY | --ha-service SERVICE | --no-notify]
  people.py key NAME              new gateway key for a person (shown once)
  people.py attach NAME ENTRY...  give a person registry entries
  people.py detach NAME ENTRY...
  people.py share ENTRY...        household entries (anyone, incl. satellites)
  people.py unshare ENTRY...
  people.py banks                 create any Hindsight bank the registry names but Hindsight lacks
  people.py rename OLD NEW [--auth VAR] [--service S --instance I --user U]
                                  rename a registry entry everywhere it is named: the
                                  registry, each person's list, gateway overrides
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


def hindsight_banks() -> dict[str, str]:
    """bank -> base URL, for every Hindsight entry (one bank per URL path)."""
    out = {}
    for e in load(REGISTRY).get("servers") or []:
        m = re.match(r"^(https?://[^/]+)/mcp/([A-Za-z0-9_-]+)/?$", e.get("url") or "")
        if m and "EDIT-ME" not in m.group(1):
            out[m.group(2)] = m.group(1)
    return out


def ensure_banks(only=None) -> int:
    """Hindsight creates a bank on its first write, so a new person's bank (or the
    household's) does not exist yet and every recall says 'Bank not found'. Create
    the missing ones now. Needs HINDSIGHT_API_KEY in the environment; says so and
    carries on if it cannot (the bank then appears with the first memory)."""
    import json
    import urllib.error
    import urllib.request
    key = os.environ.get("HINDSIGHT_API_KEY", "")
    banks = {b: u for b, u in hindsight_banks().items() if not only or b in only}
    if not banks:
        return 0
    if not key or key in ("set-in-keychain", "EDIT-ME", "changeme"):
        say("HINDSIGHT_API_KEY not available here: banks will be created by their first memory.")
        return 0
    def call(base, method, path, body=None):
        r = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                                   method=method, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(r, timeout=15) as resp:
            return json.load(resp)
    done = 0
    for bank, base in banks.items():
        try:
            have = {b["bank_id"] for b in call(base, "GET", "/v1/default/banks").get("banks", [])}
            if bank in have:
                continue
            call(base, "PUT", f"/v1/default/banks/{bank}", {})
            say(f"Created Hindsight bank '{bank}'.")
            done += 1
        except (urllib.error.URLError, OSError, ValueError) as exc:
            say(f"Could not reach Hindsight at {base} to create '{bank}' ({exc}); it will appear with its first memory.")
    return done


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

    bank_entry = f"hindsight-{name}"
    if bank_entry in registry_entries():
        # The entry is already in the registry (made earlier with `novak add`, or by
        # a previous attempt). Reuse it: this person's bank is that entry.
        say(f"Using the existing memory bank entry {bank_entry}.")
        if bank_entry not in entries:
            entries.append(bank_entry)
        ensure_banks([name])
    elif a.bank or (not a.yes and instances.yn(answers, "bank", f"Create a Hindsight memory bank '{name}'?", True)):
        cmd = [sys.executable, str(Path(instances.__file__)), "add", "--kind", "hindsight", "--name", name,
               "--set", "voice_safe=n", "--accepted-by", a.accepted_by or os.environ.get("USER", "admin"), "--yes"]
        r = subprocess.run(cmd, env={**os.environ, "NOVAK_HOME": str(NOVAK_HOME)})
        if r.returncode != 0:
            raise SystemExit("could not add the memory bank; person not created")
        entries.append(f"hindsight-{name}")
        ensure_banks([name])

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


def cmd_set(a):
    """Change a person's sign-in names, emails or confirmation channel."""
    need_files()
    d = load(PEOPLE)
    p = person_or_die(d, a.name)
    if a.names:
        p["names"] = [n for n in a.names.split(",") if n]
    if a.emails is not None:
        p["emails"] = [e for e in a.emails.split(",") if e]
    if a.ticker:
        p["notify"] = {"kind": "ticker", "category": a.ticker}
    elif a.ha_service:
        p["notify"] = {"kind": "ha", "service": a.ha_service}
    elif a.no_notify:
        p.pop("notify", None)
    backup(PEOPLE)
    write_block(PEOPLE, a.name, 2, p)
    say(f"{a.name}: names {p.get('names')}, emails {p.get('emails')}, notify {p.get('notify') or 'none'}")
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


def cmd_banks(a):
    ensure_banks()
    return 0


def entry_block(lines, name):
    """(start, end) of the registry entry `- name: <name>`: from its first line to the
    line before the next entry, not counting comments that introduce that next one."""
    pat = re.compile(rf"^(\s*)- name: {re.escape(name)}\s*$")
    start = next((i for i, l in enumerate(lines) if pat.match(l)), None)
    if start is None:
        return None
    ind = len(pat.match(lines[start]).group(1))
    end = len(lines)
    for j in range(start + 1, len(lines)):
        l = lines[j]
        if re.match(rf"^\s{{{ind}}}- ", l) or (l.strip() and not l.lstrip().startswith("#") and len(l) - len(l.lstrip()) <= ind):
            end = j
            break
    while end > start + 1 and (not lines[end - 1].strip() or lines[end - 1].lstrip().startswith("#")):
        end -= 1
    return start, end


def cmd_rename(a):
    need_files()
    old, new = a.old, a.new
    if not NAME_RE.match(new):
        raise SystemExit(f"'{new}' is not a valid entry name (a-z, 0-9, hyphens)")
    names = registry_entries()
    if old not in names:
        raise SystemExit(f"no such entry: {old}")
    if new != old and new in names:
        raise SystemExit(f"'{new}' already exists")
    lines = REGISTRY.read_text().splitlines(True)
    rng = entry_block(lines, old)
    if rng is None:
        raise SystemExit(f"could not find the block for {old} in {REGISTRY.name}")
    block = lines[rng[0]:rng[1]]
    lead = re.match(r"^(\s*)- name:", block[0]).group(1)          # the list's own indent
    f = lead + "  "                                                  # the indent of the entry's fields
    old_auth = next((re.match(rf"^{f}auth: (\S+)", l).group(1) for l in block if re.match(rf"^{f}auth: \S+", l)), None)
    block[0] = f"{lead}- name: {new}\n"
    block = [l for l in block if not re.match(rf"^{f}(service|instance|user): ", l)]
    extra = []
    if a.service: extra.append(f"{f}service: {a.service}\n")
    if a.instance: extra.append(f"{f}instance: '{a.instance}'\n")
    if a.user: extra.append(f"{f}user: {a.user}\n")
    block[1:1] = extra
    if a.auth:
        if old_auth is None:
            raise SystemExit(f"{old} has no auth variable to rename")
        block = [re.sub(rf"^({f}auth: )\S+", rf"\g<1>{a.auth}", l) for l in block]
    backups = [(REGISTRY, backup(REGISTRY)), (PEOPLE, backup(PEOPLE))]
    lines[rng[0]:rng[1]] = block
    REGISTRY.write_text("".join(lines))

    d = load(PEOPLE)
    hh = d.get("household") or {}
    if old in (hh.get("entries") or []):
        hh["entries"] = [new if e == old else e for e in hh["entries"]]
        write_block(PEOPLE, "household", 0, hh)
    for pname, person in people_entries(d).items():
        if old in ((person or {}).get("entries") or []):
            person["entries"] = [new if e == old else e for e in person["entries"]]
            write_block(PEOPLE, pname, 2, person)
    if GATEWAY.exists():
        g = GATEWAY.read_text()
        g2 = re.sub(rf"^(\s+){re.escape(old)}:", rf"\g<1>{new}:", g, flags=re.M)
        if g2 != g:
            backups.append((GATEWAY, backup(GATEWAY)))
            GATEWAY.write_text(g2)
    problem = instances.validate(REGISTRY)
    if problem:
        for target, bak in backups:
            shutil.copy2(bak, target)
        raise SystemExit(f"the registry did not validate after renaming, so everything was put back:\n{problem}")
    say(f"Renamed {old} to {new} (backups kept as .bak-<time>).")
    if a.auth and old_auth and a.auth != old_auth:
        say(f"The credential variable is now {a.auth}; its value must move from {old_auth}.")
        print(f"MOVE_SECRET: {old_auth} {a.auth}")
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
    if a.name == "ingest":
        say("Store it for the ingest service:  novak secret set INGEST_GATEWAY_KEY   then  novak up")
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
    st = sub.add_parser("set"); st.add_argument("name")
    st.add_argument("--names"); st.add_argument("--emails")
    st.add_argument("--ticker"); st.add_argument("--ha-service"); st.add_argument("--no-notify", action="store_true")
    k = sub.add_parser("key"); k.add_argument("name")
    for c in ("attach", "detach"):
        x = sub.add_parser(c); x.add_argument("name"); x.add_argument("entries", nargs="+")
    for c in ("share", "unshare"):
        x = sub.add_parser(c); x.add_argument("entries", nargs="+")
    c = sub.add_parser("client"); c.add_argument("name")
    sub.add_parser("household-key")
    sub.add_parser("banks")
    r = sub.add_parser("rename")
    r.add_argument("old"); r.add_argument("new")
    r.add_argument("--auth"); r.add_argument("--service"); r.add_argument("--instance"); r.add_argument("--user")
    a = ap.parse_args()
    return {"add": cmd_add, "list": cmd_list, "set": cmd_set, "key": cmd_key, "attach": lambda a: cmd_attach(a),
            "detach": lambda a: cmd_attach(a, True), "share": lambda a: cmd_share(a),
            "unshare": lambda a: cmd_share(a, True), "client": cmd_client,
            "household-key": cmd_household_key, "banks": cmd_banks, "rename": cmd_rename}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
