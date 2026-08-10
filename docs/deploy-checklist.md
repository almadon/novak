# Deploy checklist (run on the mini)

This repo was authored off-host. Everything below is either a one-time
manual step or a detail that could not be verified without the host —
work top to bottom.

## Bootstrap

- [ ] `./scripts/bootstrap.sh`
- [ ] If the oMLX brew install fails, install from <https://omlx.ai> and re-run.
- [ ] Login items: OrbStack + oMLX added; auto-login enabled.
- [ ] `pmset -g custom` shows sleep 0, autorestart 1.

## oMLX (see ../omlx/SETTINGS.md)

- [ ] Note the server port → set `OMLX_PORT` in `.env`.
- [ ] Enable API-key auth → Keychain item `novak/OMLX_API_KEY`.
- [ ] Bind to LAN; confirm reachable from another machine: `curl http://<mini>:<port>/v1/models`
- [ ] Download Qwen3-4B-Instruct 4bit + Qwen3-14B 4bit (admin UI → HF search).
- [ ] Set idle TTL on the 14B (15–30 min); none on the 4B.
- [ ] Create profiles `ha-voice`, `chat`, `deep`.
- [ ] **Verify** whether oMLX serves `/v1/embeddings`; if not, use clients' built-in local embedders.
- [ ] Confirm oMLX auto-starts after a reboot (launch-at-login setting or a launchd agent).

## Secrets

- [ ] `security add-generic-password -s "novak/OMLX_API_KEY" -a novak -w`
- [ ] Same for `OUTLINE_API_KEY` (created read-only in Outline) and `VIKUNJA_API_TOKEN`.
- [ ] `.env` has no real secrets in it.

## Docker stack — items to verify on first `./scripts/up.sh`

- [ ] **supergateway flags**: `--outputTransport streamableHttp` is current
      usage — check `npx supergateway --help` if a container crash-loops.
- [ ] **outline-mcp-server env var names** (`OUTLINE_API_URL`/`OUTLINE_API_KEY`)
      against its README; it may also support native HTTP mode, which would
      let you drop supergateway for that service.
- [ ] **OpenMemory images/config**: `mem0/openmemory-mcp` + `mem0/openmemory-ui`
      tags exist and start; configure its LLM + embedder to point at
      **local** endpoints (oMLX / local embedder), *not* OpenAI — this is the
      one service that defaults to a cloud key. Check its settings screen.
      Note the exact MCP endpoint path for clients.
- [ ] Wyoming images run on arm64 (`rhasspy/wyoming-whisper`, `rhasspy/wyoming-piper`).
- [ ] `docker compose ps` — everything `running`, nothing restarting.

## Open WebUI

- [ ] First account created = admin; then disable open signup
      (Admin → Settings → Users).
- [ ] Models from oMLX (incl. profiles) appear in the model switcher.
- [ ] Register MCP servers (Admin → Settings → Tools, native MCP/streamable-HTTP):
      Outline `http://<mini>:8001/mcp`, Vikunja `http://<mini>:8002/mcp`,
      OpenMemory per its path.
- [ ] Voice call mode works (local Whisper STT + TTS in Audio settings).
- [ ] Create per-user accounts; check user A cannot see user B's chats.

## Home Assistant (see home-assistant.md)

- [ ] HACS: install openai-compatible-conversation (or Extended OpenAI
      Conversation for function-calling device control).
- [ ] Wyoming integrations: STT 10300, TTS 10200.
- [ ] MCP integration(s): OpenMemory (+ Outline if desired).
- [ ] Assist pipeline assembled; test from an HA Voice device:
      a device command, then a memory question ("what do you know about me?").

## Resilience test (do this once)

- [ ] Pull the power. On reboot: auto-login → OrbStack + containers up,
      oMLX up with 4B loaded → HA voice works within a few minutes,
      hands-off.
- [ ] Reboot again while a chat is open — Open WebUI session survives,
      history intact.

## Later / optional

- [ ] Tailscale for remote access (no port forwarding, ever).
- [ ] Kokoro TTS swap if piper voices disappoint.
- [ ] Email MCP (read-only first — see security.md Rule 3 before enabling send).
- [ ] Time Machine includes OrbStack volumes + `~/.omlx`.
