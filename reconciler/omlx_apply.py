#!/usr/bin/env python3
"""
Applies registry/omlx.yaml to oMLX by writing its own JSON files.

Not through oMLX's admin API, deliberately: that needs an admin session
separate from OMLX_API_KEY, and holding a second credential here would undo the
property that makes this repo's appliers safe — see decision 17 in
docs/decisions.md. oMLX stores this state as JSON anyway.

Invariants worth preserving if you edit this:
  * Diff first. Writing these files means restarting oMLX, which drops loaded
    models. When nothing differs this must be a no-op and must NOT restart, so
    it is safe to call from up.sh on every run.
  * Fail loudly. The on-disk format is undocumented and version-coupled. A
    field oMLX no longer recognises must stop the run, never be silently
    dropped — a profile that quietly did not take is the failure this exists
    to prevent.
  * Never write under a running server. oMLX holds this state in memory and
    rewrites the file on its own saves, so it is stopped first.
  * Verify by observation. After restarting, the exposed profiles must appear
    in /v1/models. If they do not, say so rather than reporting success.

Usage:
    ./omlx_apply.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML required")

REPO_DIR = Path(__file__).resolve().parent.parent
NOVAK_HOME = Path(os.environ.get("NOVAK_HOME", Path.home() / ".novak"))
OMLX_HOME = Path(os.environ.get("OMLX_HOME", Path.home() / ".omlx"))
OMLX_BIN = OMLX_HOME / "bin" / "omlx"

_deployed = NOVAK_HOME / "registry" / "omlx.yaml"
REGISTRY = _deployed if _deployed.exists() else REPO_DIR / "registry" / "omlx.yaml"

SETTINGS_FILE = OMLX_HOME / "model_settings.json"
PROFILES_FILE = OMLX_HOME / "model_profiles.json"
OMLX_SETTINGS = OMLX_HOME / "settings.json"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")

# Fallback copy of oMLX's profile field list, used only when its source cannot
# be read. Kept deliberately small: the real list is read from the installed
# app below, so this never silently goes stale against a newer oMLX.
FALLBACK_FIELDS = {
    "max_context_window", "max_tokens", "temperature", "top_p", "top_k",
    "min_p", "repetition_penalty", "presence_penalty", "force_sampling",
    "enable_thinking", "preserve_thinking", "thinking_budget_enabled",
    "thinking_budget_tokens", "reasoning_parser", "guided_grammar_enabled",
    "guided_grammar", "max_tool_result_tokens", "chat_template_kwargs",
    "forced_ct_kwargs",
}

APP_PROFILES_PY = Path(
    "/Applications/oMLX.app/Contents/Resources/omlx/model_profiles.py"
)


class Fail(Exception):
    pass


def known_fields() -> tuple[set[str], str]:
    """
    oMLX's own accepted profile fields, read from the installed app so this
    tracks the version actually running rather than the one it was written
    against. Falls back to the copy above when the app is not where we expect.
    """
    if APP_PROFILES_PY.exists():
        text = APP_PROFILES_PY.read_text()
        found: set[str] = set()
        for const in ("UNIVERSAL_PROFILE_FIELDS", "MODEL_SPECIFIC_PROFILE_FIELDS"):
            m = re.search(rf"{const}\s*=\s*\((.*?)\)", text, re.S)
            if m:
                found |= set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))
        if found:
            return found, f"read from {APP_PROFILES_PY.name}"
    return set(FALLBACK_FIELDS), "built-in fallback list"


def load_registry() -> list[dict]:
    if not REGISTRY.exists():
        raise Fail(f"registry not found: {REGISTRY}")
    doc = yaml.safe_load(REGISTRY.read_text()) or {}
    models = doc.get("models")
    if not isinstance(models, list) or not models:
        raise Fail("omlx.yaml: top-level 'models' must be a non-empty list")
    return models


def served_models(base_url: str, api_key: str) -> list[str]:
    req = urllib.request.Request(f"{base_url}/v1/models")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return [m["id"] for m in json.load(r).get("data", [])]


def build_desired(models: list[dict], available: list[str], fields: set[str]):
    """Desired contents of model_settings.json and model_profiles.json."""
    settings: dict[str, dict] = {}
    profiles: dict[str, dict] = {}

    for m in models:
        repo = m.get("repo")
        if not repo:
            raise Fail("every model needs a 'repo'")
        # oMLX serves models under the leaf of the HuggingFace repo id.
        model_id = repo.split("/")[-1]
        if model_id not in available:
            raise Fail(
                f"{model_id} is not served by oMLX (from repo {repo}).\n"
                f"  Available: {', '.join(available) or 'none'}\n"
                f"  Download it in oMLX before applying profiles for it."
            )

        if "ttl_seconds" not in m:
            raise Fail(f"[{model_id}] ttl_seconds is required (null = never unload)")
        ttl = m["ttl_seconds"]
        if ttl is not None:
            if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
                raise Fail(f"[{model_id}] ttl_seconds must be a positive int or null")
            # None is oMLX's "no TTL", and its writer omits None entirely, so
            # matching that keeps our output byte-comparable with its own.
            settings[model_id] = {"ttl_seconds": ttl}

        for p in m.get("profiles") or []:
            name = p.get("name")
            if not isinstance(name, str) or not NAME_RE.match(name):
                raise Fail(f"[{model_id}] invalid profile name {name!r} "
                           f"(expected ^[a-z0-9][a-z0-9_-]{{0,31}}$)")
            pf = p.get("fields") or {}
            if not isinstance(pf, dict) or not pf:
                raise Fail(f"[{model_id}/{name}] 'fields' must be a non-empty mapping")
            unknown = sorted(set(pf) - fields)
            if unknown:
                raise Fail(
                    f"[{model_id}/{name}] oMLX does not accept: {', '.join(unknown)}\n"
                    f"  Either the name is wrong or this oMLX version renamed it.\n"
                    f"  Refusing rather than dropping it silently."
                )
            profiles.setdefault(model_id, {})[name] = {
                "name": name,
                "display_name": name,
                "api_name": name,
                "description": p.get("description"),
                "settings": dict(pf),
                "source_template": None,
                # Without this the profile exists but no client can select it.
                "expose_as_model": True,
            }
    return settings, profiles


def read_json(path: Path, key: str) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()).get(key, {}) or {}
    except json.JSONDecodeError as e:
        raise Fail(f"{path} is not valid JSON ({e}); refusing to overwrite it")


def comparable(profiles: dict) -> dict:
    """Profiles minus oMLX's own bookkeeping, so timestamps are not drift."""
    out = {}
    for model_id, per in profiles.items():
        out[model_id] = {
            n: {k: v for k, v in rec.items()
                if k not in ("created_at", "updated_at")}
            for n, rec in per.items()
        }
    return out


def write_atomic(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    tmp.replace(path)


def omlx(*args: str) -> None:
    if not OMLX_BIN.exists():
        raise Fail(f"oMLX CLI not found at {OMLX_BIN}")
    subprocess.run([str(OMLX_BIN), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


def main() -> int:
    dry = "--dry-run" in sys.argv

    cfg = json.loads(OMLX_SETTINGS.read_text()) if OMLX_SETTINGS.exists() else {}
    port = (cfg.get("server") or {}).get("port", 8000)
    base_url = f"http://127.0.0.1:{port}"
    api_key = os.environ.get("OMLX_API_KEY", "")

    fields, field_src = known_fields()
    models = load_registry()

    try:
        available = served_models(base_url, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
        raise Fail(
            f"cannot reach oMLX at {base_url} ({e}).\n"
            f"  It must be running to apply profiles — start it, then re-run."
        )

    want_settings, want_profiles = build_desired(models, available, fields)

    have_settings = read_json(SETTINGS_FILE, "models")
    have_profiles = read_json(PROFILES_FILE, "profiles")

    # Only compare the keys we manage; anything set in oMLX's UI that we do not
    # declare is left alone rather than reverted.
    settings_drift = any(
        (have_settings.get(mid) or {}).get("ttl_seconds") != s.get("ttl_seconds")
        for mid, s in want_settings.items()
    ) or any(
        mid not in want_settings and (have_settings.get(mid) or {}).get("ttl_seconds")
        is not None for mid in ()
    )
    profiles_drift = comparable(want_profiles) != comparable(
        {k: v for k, v in have_profiles.items() if k in want_profiles}
    )

    print(f"fields:   {len(fields)} accepted ({field_src})")
    for mid, per in want_profiles.items():
        print(f"model:    {mid} -> {', '.join(f'{mid}:{n}' for n in per)}")

    if not settings_drift and not profiles_drift:
        print("no change — oMLX already matches the registry")
        return 0

    if dry:
        print("would write:")
        print(f"  {SETTINGS_FILE}")
        print(f"  {PROFILES_FILE}")
        print("  (and restart oMLX, which drops loaded models)")
        return 0

    # Merge rather than replace: preserve models and profiles we do not declare.
    merged_settings = dict(have_settings)
    for mid, s in want_settings.items():
        merged_settings[mid] = {**(merged_settings.get(mid) or {}), **s}
    merged_profiles = dict(have_profiles)
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    for mid, per in want_profiles.items():
        existing = merged_profiles.get(mid) or {}
        for n, rec in per.items():
            prev = existing.get(n) or {}
            existing[n] = {**rec,
                           "created_at": prev.get("created_at", now),
                           "updated_at": now}
        merged_profiles[mid] = existing

    print("stopping oMLX (its own saves would overwrite these files)")
    omlx("stop")
    write_atomic(SETTINGS_FILE, {"version": 1, "models": merged_settings})
    write_atomic(PROFILES_FILE, {"version": 1, "profiles": merged_profiles})
    print(f"wrote {SETTINGS_FILE.name} and {PROFILES_FILE.name}")
    omlx("start")

    # Observation, not assumption: the exposed ids must actually show up.
    expected = {f"{mid}:{n}" for mid, per in want_profiles.items() for n in per}
    for attempt in range(12):
        time.sleep(5)
        try:
            now_served = set(served_models(base_url, api_key))
        except Exception:
            continue
        if expected <= now_served:
            print(f"verified: {len(expected)} profile(s) served by oMLX")
            return 0
    missing = sorted(expected - set(served_models(base_url, api_key)))
    raise Fail(
        "profiles were written but oMLX is not serving them: "
        + ", ".join(missing)
        + "\n  The model_id key or the record shape may differ in this oMLX "
          "version. The files were changed — check oMLX's admin panel."
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        sys.exit(f"✋ {e}")
