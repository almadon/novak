#!/usr/bin/env python3
"""
Checks that Home Assistant's synced copy of the voice persona is current.

HA pulls prompts/novak-voice.md (decision #53): a REST sensor polls
persona/server.py, and the `litellm` agent's Instructions field is a
template that reads the sensor's `text` attribute. So there is no pasted
copy to drift. What can still go wrong is the pull itself: the sensor is
missing, unavailable, or stale because the server or HA's polling stopped.
This compares the sensor's text with the repo's file and says which.

This replaces decision #52's version, which tried to read the Instructions
field itself. HA's websocket API does not return a conversation agent's
settings to anyone (only IDs and titles), so that check could never work,
and the only other route needs an admin token. Reading one entity's state
works for any user, including the dedicated non-admin HA user the token
should belong to (HA tokens carry no scope of their own, so a non-admin
user is what makes this read-only).

What this does NOT prove: that the Instructions field actually contains the
template. HA gives no read access to that, so confirm it once by asking
`ha-voice` who it is.

Usage:
    HA_URL=http://ha.local HA_DRIFT_TOKEN=... ./ha_persona_drift.py

Exit codes: 0 = in sync, 1 = drift found, 2 = could not check.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PERSONA_FILE = REPO_DIR / "prompts" / "novak-voice.md"
SENSOR_ENTITY = "sensor.novak_voice_persona"


def _load_persona() -> str:
    """Same header-stripping rule as router/persona_hook.py's _load_persona."""
    text = PERSONA_FILE.read_text()
    _, _, body = text.partition("\n---\n")
    return body.strip() or text.strip()


def _fetch_sensor(ha_url: str, token: str) -> dict:
    req = urllib.request.Request(
        f"{ha_url.rstrip('/')}/api/states/{SENSOR_ENTITY}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def main() -> int:
    ha_url = os.environ.get("HA_URL", "").strip()
    token = os.environ.get("HA_DRIFT_TOKEN", "").strip()
    if not ha_url or not token or token == "set-in-keychain":
        print(
            "HA_URL and/or HA_DRIFT_TOKEN not configured, skipping the "
            "HA-side persona check. See docs/home-assistant.md.",
            file=sys.stderr,
        )
        return 2
    if not PERSONA_FILE.exists():
        print(f"cannot find {PERSONA_FILE}", file=sys.stderr)
        return 2

    try:
        state = _fetch_sensor(ha_url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            print("HA rejected HA_DRIFT_TOKEN (401).", file=sys.stderr)
        elif exc.code == 404:
            print(
                f"{SENSOR_ENTITY} does not exist on HA. The REST sensor from "
                "docs/home-assistant.md is not set up (or is named differently).",
                file=sys.stderr,
            )
        else:
            print(f"HA answered {exc.code} for {SENSOR_ENTITY}.", file=sys.stderr)
        return 2
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"could not reach HA at {ha_url}: {exc}", file=sys.stderr)
        return 2

    if state.get("state") in ("unavailable", "unknown"):
        print(
            f"{SENSOR_ENTITY} is {state.get('state')}: HA cannot reach the "
            "persona server (check the persona container and HA's route to it).",
            file=sys.stderr,
        )
        return 2

    live = str(state.get("attributes", {}).get("text", "")).strip()
    master = _load_persona().strip()
    if live == master:
        print("HA's synced persona matches prompts/novak-voice.md.")
        return 0

    print("HA's synced persona differs from prompts/novak-voice.md.")
    print("  If you just edited prompts/, HA picks it up at its next poll (see")
    print("  scan_interval in docs/home-assistant.md). If this persists, the")
    print("  pull is stuck.")
    print(f"  repo: {len(master)} chars   HA sensor: {len(live)} chars")
    return 1


if __name__ == "__main__":
    sys.exit(main())
