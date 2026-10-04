#!/usr/bin/env python3
"""
Checks whether Home Assistant's own copy of prompts/novak-voice.md — pasted
into the `litellm` conversation agent's Instructions field (decision #42) —
has drifted from the master file.

This is the *other* half of decision #18's original persona-drift problem.
Decision #44 built the half that's actually bitten this project (a client
silently sending its own system message, caught by grepping the router's
logs). This half is different in kind: HA's Instructions field is a
*deliberate*, independently-maintained second copy of the persona text, not
an accident, so there's no "injection skipped" event to log — the only way
to catch drift here is to read HA's own config and diff it against the repo.

That needs HA's own API and a dedicated, read-only-in-practice long-lived
access token (HA_DRIFT_TOKEN) — deliberately NOT the same token as
HA_MCP_TOKEN, which belongs to the `ha-mcp` registry entry (88+ tools,
including YAML/file edits) and would be borrowing far more scope than a
one-field text diff needs. See docs/home-assistant.md for where to create
the token, and decision #52 for why a *dedicated HA user* matters here too:
Home Assistant's long-lived access tokens carry no scope of their own — a
token inherits whatever the user it belongs to can do, in full. A read-only
check is only actually read-only if the account behind the token is.

HA has no REST endpoint for config entry options (the frontend itself uses
the websocket API for this) — so this talks to `/api/websocket` instead of
plain HTTP, using the `websockets` package rather than a hand-rolled client.

Requires `websockets`:  pip3 install --user websockets

### Built blind, same as decision #44's other half was

There is no live HA instance reachable from where this was written, so the
one part of this script that could NOT be checked directly is the shape of
a `litellm` config entry's subentry data — specifically, which key holds
the Instructions text. INSTRUCTION_KEYS below is a best guess at the
plausible names; rather than silently comparing against the wrong key and
reporting false "no drift," a subentry that doesn't contain exactly one of
them is treated as unrecognized and printed raw, so a human can add the
real key name here after seeing it once against a live deployment. **VERIFY
this whole script against Spire's real HA instance before trusting its
output** — see docs/STATE.md's Open VERIFY list.

Usage:
    HA_URL=http://ha.local:8123 HA_DRIFT_TOKEN=... ./ha_persona_drift.py

Exit codes: 0 = no drift found, 1 = drift found, 2 = could not check
(unreachable, auth failure, or the subentry shape didn't match).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

try:
    import websockets
except ImportError:
    websockets = None  # checked in main(), after the cheaper env-var check

REPO_DIR = Path(__file__).resolve().parent.parent
PERSONA_FILE = REPO_DIR / "prompts" / "novak-voice.md"

# The litellm integration's own domain string, as it appears in HA's config
# entries — not to be confused with the `litellm` model role names
# (chat/deep/ha-voice) persona_hook.py maps in PERSONA_MAP.
LITELLM_DOMAIN = "litellm"

# The role name HA's Instructions field is standing in for, matching
# router/persona_hook.py's PERSONA_MAP entry for "ha-voice". Used only to
# pick the right subentry when a litellm config entry has more than one
# conversation agent configured (decision #42 mentions chat/ha-voice/deep/
# task as the roles a single entry can expose).
TARGET_AGENT_NAME = "ha-voice"

# Best-guess keys for where the pasted Instructions text lives inside a
# conversation-agent subentry's `data` dict. Unverified — see module
# docstring. Checked in order; first match wins.
INSTRUCTION_KEYS = ("instructions", "prompt", "system_prompt", "instructions_prompt")


def _load_persona() -> str:
    """Same header-stripping rule as router/persona_hook.py's _load_persona."""
    text = PERSONA_FILE.read_text()
    _, _, body = text.partition("\n---\n")
    return (body.strip() or text.strip()) + "\n"


async def _fetch_ha_instructions(ha_url: str, token: str) -> tuple[str | None, dict]:
    """
    Returns (instructions_text_or_None, raw_subentry_data_for_diagnostics).

    None means "connected fine, but couldn't find a recognizable ha-voice
    conversation-agent subentry" — the caller treats that as a hard failure,
    not as "no drift."
    """
    scheme = "wss" if ha_url.startswith("https") else "ws"
    host = ha_url.split("://", 1)[-1].rstrip("/")
    ws_url = f"{scheme}://{host}/api/websocket"

    async with websockets.connect(ws_url, open_timeout=10) as ws:
        hello = json.loads(await ws.recv())
        if hello.get("type") != "auth_required":
            raise RuntimeError(f"unexpected handshake from {ws_url}: {hello}")

        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth_result = json.loads(await ws.recv())
        if auth_result.get("type") != "auth_ok":
            raise RuntimeError(
                f"HA rejected HA_DRIFT_TOKEN ({auth_result.get('message', auth_result)})"
            )

        msg_id = 1

        async def call(payload: dict) -> dict:
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({**payload, "id": msg_id}))
            while True:
                result = json.loads(await ws.recv())
                if result.get("id") == msg_id:
                    return result

        entries = await call({"type": "config_entries/get"})
        litellm_entries = [
            e for e in entries.get("result", []) if e.get("domain") == LITELLM_DOMAIN
        ]
        if not litellm_entries:
            raise RuntimeError(
                f"no '{LITELLM_DOMAIN}' config entry found on this HA instance "
                "— is the integration actually added? (Settings -> Devices & "
                "Services -> LiteLLM)"
            )

        for entry in litellm_entries:
            subentries = await call(
                {
                    "type": "config_entries/subentries/list",
                    "config_entry_id": entry["entry_id"],
                }
            )
            for sub in subentries.get("result", []):
                data = sub.get("data", {})
                title = str(sub.get("title", "")).lower()
                if TARGET_AGENT_NAME not in title and TARGET_AGENT_NAME not in str(
                    data
                ).lower():
                    continue
                for key in INSTRUCTION_KEYS:
                    if key in data and isinstance(data[key], str):
                        return data[key], data
                # Found the right agent, but none of the guessed keys matched.
                return None, data

    return None, {}


def main() -> int:
    ha_url = os.environ.get("HA_URL", "").strip()
    token = os.environ.get("HA_DRIFT_TOKEN", "").strip()
    if not ha_url or not token or token == "set-in-keychain":
        print(
            "HA_URL and/or HA_DRIFT_TOKEN not configured — skipping the "
            "HA-side persona check. See docs/home-assistant.md.",
            file=sys.stderr,
        )
        return 2

    if not PERSONA_FILE.exists():
        print(f"cannot find {PERSONA_FILE}", file=sys.stderr)
        return 2

    if websockets is None:
        print(
            "the 'websockets' package is required:\n"
            "  pip3 install --user websockets",
            file=sys.stderr,
        )
        return 2

    try:
        ha_text, raw = asyncio.run(_fetch_ha_instructions(ha_url, token))
    except Exception as exc:  # noqa: BLE001 - reported to the operator, not swallowed
        print(f"could not check HA: {exc}", file=sys.stderr)
        return 2

    if ha_text is None:
        print(
            "found the ha-voice agent's config on HA, but none of the "
            f"expected keys {INSTRUCTION_KEYS} were in its data. This "
            "script's guess at the field name (see its module docstring) is "
            "wrong for this HA version. Raw subentry data, for fixing "
            f"INSTRUCTION_KEYS by hand:\n{json.dumps(raw, indent=2)}",
            file=sys.stderr,
        )
        return 2

    repo_text = _load_persona()
    if ha_text.strip() == repo_text.strip():
        print("No drift: HA's Instructions field matches prompts/novak-voice.md.")
        return 0

    print(
        "DRIFT: HA's ha-voice Instructions field no longer matches "
        "prompts/novak-voice.md.\n"
        "Re-paste the current file's body into Settings -> Devices & "
        "Services -> LiteLLM -> ha-voice agent -> Instructions.\n"
    )
    print("--- prompts/novak-voice.md (repo) ---")
    print(repo_text.strip())
    print("\n--- HA's Instructions field (live) ---")
    print(ha_text.strip())
    return 1


if __name__ == "__main__":
    sys.exit(main())
