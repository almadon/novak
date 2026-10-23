#!/usr/bin/env python3
"""
Applies registry/openwebui.yaml to a running Open WebUI (decision #66).

Same shape as reconcile.py and router_apply.py, pointed at a client instead of a
container: it reads a file, validates it, and makes the live system match. Open WebUI
keeps its tool connections and model presets in its own database, so without this they
are whatever someone last clicked.

Deliberately dumb, same invariants as the other appliers:
  * Fail closed: a validation error aborts before anything is sent.
  * Secrets are never in the file. `key_env` names the variable; the value is read from
    the environment at apply time, sent to Open WebUI and never printed.
  * Only what the file names is touched. Other connections and presets are left alone,
    and a preset keeps its description, sharing and parameters: only its default tools and
    system prompt change.
  * Idempotent. A second run changes nothing and says so.

Usage:
    owui_apply.py            show what would change, change nothing (same as `drift`)
    owui_apply.py --apply    make Open WebUI match
Exit status of the default mode is 1 when Open WebUI differs from the file.

Environment: OWUI_ADMIN_API_KEY (an admin API key), the keys named by `key_env`,
OWUI_URL or OPENWEBUI_PORT, NOVAK_HOME.

Requires PyYAML:  pip3 install --user pyyaml
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required:  pip3 install --user pyyaml")

REPO = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^\S+$")
PLACEHOLDERS = ("", "set-in-keychain", "EDIT-ME", "changeme")


class ConfigError(Exception):
    pass


class ApiError(Exception):
    pass


# --- Open WebUI -------------------------------------------------------------------------
class Api:
    def __init__(self, base: str, key: str, timeout: float = 30):
        self.base, self.key, self.timeout = base.rstrip("/"), key, timeout

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(
            self.base + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            detail = exc.read().decode(errors="replace")[:200]
            if exc.code in (401, 403):
                raise ApiError(f"Open WebUI refused the admin key ({exc.code}): is OWUI_ADMIN_API_KEY an admin's key "
                               f"and OWUI_ENABLE_API_KEYS true? {detail}") from exc
            raise ApiError(f"{method} {path}: {exc.code} {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise ApiError(f"cannot reach Open WebUI at {self.base}: {exc}") from exc


# --- the file ---------------------------------------------------------------------------
def load_config(path: Path) -> dict:
    cfg = ((yaml.safe_load(path.read_text()) or {}).get("openwebui")) if path.exists() else None
    if not isinstance(cfg, dict):
        raise ConfigError(f"{path} has no 'openwebui:' block")
    servers, seen = cfg.get("tool_servers") or [], set()
    for s in servers:
        for field in ("id", "name", "url"):
            if not s.get(field):
                raise ConfigError(f"tool server {s.get('id', '?')}: needs '{field}'")
        if not ID_RE.match(s["id"]) or s["id"] in seen:
            raise ConfigError(f"tool server id {s['id']!r}: must be unique and have no spaces")
        seen.add(s["id"])
        if s.get("type", "mcp") not in ("mcp", "openapi"):
            raise ConfigError(f"tool server {s['id']}: type must be mcp or openapi")
        if "key" in s:
            raise ConfigError(f"tool server {s['id']}: no 'key' here, name a secret with key_env")
    for m in cfg.get("models") or []:
        if not m.get("id") or not ID_RE.match(m["id"]):
            raise ConfigError(f"model {m.get('id')!r}: needs an id with no spaces")
        for t in m.get("tools") or []:
            if t not in seen:
                raise ConfigError(f"model {m['id']}: tool {t!r} is not a tool server in this file")
    cfg["tool_servers"], cfg["models"] = servers, cfg.get("models") or []
    return cfg


def persona_text(path: Path) -> str:
    """The text after the header block, like the router's own loader."""
    text = path.read_text()
    _, _, body = text.partition("\n---\n")
    return (body.strip() or text.strip())


def system_prompt(spec: dict, repo: Path) -> str | None:
    files = spec.get("system_files") or []
    if not files:
        return None
    parts = []
    for f in files:
        p = repo / f
        if not p.exists():
            raise ConfigError(f"model {spec['id']}: system file {f} does not exist")
        parts.append(persona_text(p))
    return "\n\n".join(parts)


def tool_id(spec: dict, servers: list[dict]) -> str:
    server = next(s for s in servers if s["id"] == spec)
    return f"server:mcp:{server['id']}" if server.get("type", "mcp") == "mcp" else f"server:{server['id']}"


# --- diffing ------------------------------------------------------------------------------
def headers_of(value) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value) if value.strip() else {}
        except ValueError:
            return {"?": value}
    return dict(value or {})


def want_connection(spec: dict, existing: dict | None, env) -> dict:
    """The connection as it should be, keeping what Open WebUI holds that the file does not say."""
    conn = dict(existing or {})
    conn.update({"url": spec["url"], "path": conn.get("path", ""), "type": spec.get("type", "mcp"),
                 "auth_type": spec.get("auth_type", "bearer")})
    key = (env.get(spec["key_env"]) or "") if spec.get("key_env") else ""
    if key and key not in PLACEHOLDERS:
        conn["key"] = key
    else:
        conn.setdefault("key", None)           # no value here: keep whatever Open WebUI has
    live_headers = (existing or {}).get("headers")
    conn["headers"] = json.dumps(spec["headers"]) if isinstance(live_headers, str) else dict(spec.get("headers") or {})
    conn["config"] = dict((existing or {}).get("config") or {"enable": True})
    conn["info"] = {**((existing or {}).get("info") or {}), "id": spec["id"], "name": spec["name"],
                    "description": spec.get("description", "")}
    return conn


def connection_diff(want: dict, have: dict | None, spec: dict, env) -> list[str]:
    if have is None:
        return ["add it"]
    out = []
    for f in ("url", "type", "auth_type"):
        if want.get(f) != have.get(f):
            out.append(f"{f}: {have.get(f)!r} -> {want.get(f)!r}")
    if headers_of(want.get("headers")) != headers_of(have.get("headers")):
        out.append("headers differ")
    for f in ("name", "description"):
        if (want["info"].get(f) or "") != ((have.get("info") or {}).get(f) or ""):
            out.append(f"{f} differs")
    key = (env.get(spec.get("key_env") or "") or "")
    if key and key not in PLACEHOLDERS and key != (have.get("key") or ""):
        out.append("key differs")
    return out


def model_changes(spec: dict, have: dict | None, servers: list[dict], repo: Path):
    """(new model form, [what changed]) for one preset; the form is None when nothing changes."""
    tools = [tool_id(t, servers) for t in spec.get("tools") or []]
    system = system_prompt(spec, repo)
    if have is None:
        meta = {"toolIds": tools, "capabilities": {}}
        params = {"system": system} if system else {}
        return ({"id": spec["id"], "name": spec.get("name", spec["id"]), "meta": meta, "params": params,
                 "is_active": True}, ["create the preset"])
    meta, params, what = dict(have.get("meta") or {}), dict(have.get("params") or {}), []
    current = list(meta.get("toolIds") or [])
    merged = current + [t for t in tools if t not in current]       # ours added, anything else kept
    if merged != current:
        meta["toolIds"] = merged
        what.append("default tools: " + ", ".join(t for t in tools if t not in current) + " on")
    if system is not None and params.get("system") != system:
        what.append("system prompt updated" if params.get("system") else "system prompt set")
        params["system"] = system
    if not what:
        return None, []
    return ({"id": have["id"], "name": have.get("name") or spec["id"], "base_model_id": have.get("base_model_id"),
             "meta": meta, "params": params, "is_active": have.get("is_active", True)}, what)


# --- run ----------------------------------------------------------------------------------
def run(cfg: dict, api, env, repo: Path, apply: bool, out=print) -> int:
    """Prints what differs (and, with apply, fixes it). Returns how many things differed."""
    servers = cfg["tool_servers"]
    differing = 0

    live = (api.call("GET", "/api/v1/configs/tool_servers") or {}).get("TOOL_SERVER_CONNECTIONS") or []
    new, changed = list(live), False
    for spec in servers:
        idx = next((i for i, c in enumerate(new) if (c.get("info") or {}).get("id") == spec["id"]), None)
        have = new[idx] if idx is not None else None
        want = want_connection(spec, have, env)
        diff = connection_diff(want, have, spec, env)
        if not diff:
            out(f"  ok       tool server {spec['id']}")
            continue
        differing += 1
        out(f"  {'change' if have else 'add   '}   tool server {spec['id']}: {'; '.join(diff)}")
        if idx is None:
            new.append(want)
        else:
            new[idx] = want
        changed = True
    if changed and apply:
        api.call("POST", "/api/v1/configs/tool_servers", {"TOOL_SERVER_CONNECTIONS": new})

    for spec in cfg["models"]:
        have = api.call("GET", f"/api/v1/models/model?id={spec['id']}")
        form, what = model_changes(spec, have, servers, repo)
        if form is None:
            out(f"  ok       model {spec['id']}")
            continue
        differing += 1
        out(f"  {'change' if have else 'add   '}   model {spec['id']}: {'; '.join(what)}")
        if apply:
            api.call("POST", "/api/v1/models/model/update" if have else "/api/v1/models/create", form)
    return differing


def main(argv=None, env=None, api_factory=Api, out=print) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make Open WebUI match (default only reports)")
    ap.add_argument("--file", help="registry file (default $NOVAK_HOME/registry/openwebui.yaml)")
    args = ap.parse_args(argv)
    env = os.environ if env is None else env
    home = Path(env.get("NOVAK_HOME") or Path.home() / ".novak")
    path = Path(args.file) if args.file else home / "registry" / "openwebui.yaml"
    try:
        cfg = load_config(path)
        key = env.get("OWUI_ADMIN_API_KEY", "")
        if key in PLACEHOLDERS:
            raise ConfigError("OWUI_ADMIN_API_KEY is not set: make an admin API key in Open WebUI "
                              "(Settings, Account, API keys) and `novak secret set OWUI_ADMIN_API_KEY`")
        url = cfg.get("url") or env.get("OWUI_URL") or f"http://127.0.0.1:{env.get('OPENWEBUI_PORT') or '13400'}"
        # Validate everything that needs no network before the first request.
        for m in cfg["models"]:
            system_prompt(m, REPO)
        out(f"Open WebUI at {url}:")
        differing = run(cfg, api_factory(url, key), env, REPO, args.apply, out)
    except (ConfigError, ApiError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not differing:
        out("Open WebUI matches the file.")
        return 0
    out(("Applied." if args.apply else "Run again with --apply to make these changes.") if differing else "")
    return 0 if args.apply else 1


if __name__ == "__main__":
    sys.exit(main())
