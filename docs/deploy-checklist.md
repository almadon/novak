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
- [ ] **Verify** whether oMLX profiles carry a system prompt. If yes, paste
      the personas from `prompts/` there (one place, every client inherits).
      If no, set them per client and keep `prompts/` as the master copy.
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
- [ ] Wyoming images run on arm64 (`rhasspy/wyoming-whisper`, `rhasspy/wyoming-piper`,
      `rhasspy/wyoming-openwakeword`).
- [ ] **openwakeword will crash-loop until a matching model exists** — either
      train `hey_novak` (see ../wakeword/README.md) and put it in
      `wakeword/models/`, or set `WAKEWORD_MODEL` to a stock word for now.
      Confirm the model file extension the current image expects (`.tflite`
      vs `.onnx`) — docs mention both.
- [ ] `docker compose ps` — everything `running`, nothing restarting.

## Open WebUI

- [ ] First account created = admin; then disable open signup
      (Admin → Settings → Users).
- [ ] Models from oMLX (incl. profiles) appear in the model switcher.
- [ ] Novak persona applied (oMLX profile, or Open WebUI model preset if not).
      Sanity check: ask "who are you?" — it should answer as Novak. Then ask
      it for an API key and confirm it declines.
- [ ] Register MCP servers (Admin → Settings → Tools, native MCP/streamable-HTTP):
      Outline `http://<mini>:8001/mcp`, Vikunja `http://<mini>:8002/mcp`,
      OpenMemory per its path.
- [ ] Voice call mode works (local Whisper STT + TTS in Audio settings).
- [ ] Create per-user accounts; check user A cannot see user B's chats.

## Home Assistant (see home-assistant.md)

- [ ] HACS: install openai-compatible-conversation (or Extended OpenAI
      Conversation for function-calling device control).
- [ ] Wyoming integrations: STT 10300, TTS 10200, wake word 10400.
- [ ] MCP integration(s): OpenMemory (+ Outline if desired).
- [ ] Decide the wake-word path: trained `hey_novak` for Wyoming satellites,
      or a stock microWakeWord trigger if you're on Voice PE hardware
      (see ../wakeword/README.md — custom words aren't supported there).
- [ ] Assist pipeline named "Novak"; test from a voice device: a device
      command, then a memory question ("what do you know about me?").
- [ ] Voice answers are short (1–2 sentences) and contain no markdown —
      if they ramble, the voice persona didn't take.

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
