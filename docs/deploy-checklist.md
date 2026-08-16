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

## Before you start (off-host)

- [ ] **Lockfiles exist.** `console/package-lock.json` and
      `memory-mcp/package-lock.json` are committed. Without them the Docker
      build fails on `npm ci` — run `npm install` in each first.
- [ ] **Pocket ID client registered** for the console: `groups` scope enabled,
      redirect URI `http://<host>:3002/api/auth/callback/pocketid` for every
      hostname you'll use (LAN name *and* Tailscale name if both).
- [ ] **`admins.novak` group exists** in Pocket ID with you in it.

## Secrets

- [ ] `security add-generic-password -s "novak/OMLX_API_KEY" -a novak -w`
- [ ] Same for `OUTLINE_API_KEY` (created read-only in Outline) and `VIKUNJA_API_TOKEN`.
- [ ] Same for `CONSOLE_AUTH_SECRET` (`openssl rand -base64 32`),
      `OIDC_CLIENT_SECRET`, `MEM0_POSTGRES_PASSWORD`, `MEM0_JWT_SECRET`.
- [ ] `MEMORY_TOKEN_MAP` — JSON of `{"<token>": "<pocket-id-sub>"}`, tokens
      ≥16 chars (`openssl rand -hex 24`). Only needed once you have real users.
- [ ] `.env` has no real secrets in it.
- [ ] `./scripts/up.sh` no longer refuses to start (it checks for `changeme`).

**Ordering:** `MEM0_API_KEY` is issued by the Mem0 server on first start, so it
can't be set in advance. First run is two passes:

- [ ] `docker compose up -d mem0-db mem0` — let it bootstrap, note the key.
- [ ] `security add-generic-password -s "novak/MEM0_API_KEY" -a novak -w`
- [ ] `./scripts/up.sh` for the rest.

## Docker stack — items to verify on first `./scripts/up.sh`

- [ ] **supergateway flags**: `--outputTransport streamableHttp` is current
      usage — check `npx supergateway --help` if a container crash-loops.
- [ ] **outline-mcp-server env var names** (`OUTLINE_API_URL`/`OUTLINE_API_KEY`)
      against its README; it may also support native HTTP mode, which would
      let you drop supergateway for that service.
- [ ] **Mem0 image/tag**: `docker-compose.yml` marks the image `VERIFY` — the
      self-hosted server's image path was not confirmed off-host. Check
      upstream's own compose file.
- [ ] **Mem0 LLM + embedder point at oMLX, not OpenAI.** This is the one
      service that defaults to a cloud key; confirm the env var names against
      upstream and that no request leaves the machine.
- [ ] **Never set `AUTH_DISABLED`** on the Mem0 service — it holds every
      user's memories.
- [ ] **memory-mcp starts and answers**: `curl http://<mini>:8003/healthz`.
      Endpoint paths in `memory-mcp/src/mem0.ts` came from documentation, not
      observed traffic — expect to correct them against the real server.
- [ ] Test isolation: with two token→user entries, confirm each token sees only
      its own memories, and that `delete_memory` refuses another user's id.
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
      memory `http://<mini>:8003/mcp` **with an `Authorization: Bearer <token>`
      header** matching that user's entry in `MEMORY_TOKEN_MAP`.
- [ ] Note: Open WebUI runs on a VPS, so these URLs must be reachable from
      there — Tailscale names, not `mini.local`.
- [ ] Voice call mode works (local Whisper STT + TTS in Audio settings).
- [ ] Create per-user accounts; check user A cannot see user B's chats.

## Console (see ../console/README.md)

Nothing here has ever been built or run — expect breakage, particularly around
Auth.js v5 (still pre-1.0) and the MCP SDK API.

- [ ] `docker compose logs console` — it started rather than crash-looping.
- [ ] Sign in via Pocket ID redirects correctly and comes back.
- [ ] `/admin` loads for you (you're in `admins.novak`).
- [ ] **Test the gate that matters**: with a user *not* in `admins.novak`,
      `/admin` refuses, and a direct `PUT /api/admin/registry` returns 403 —
      not just a hidden button.
- [ ] Remove yourself from `admins.novak` in Pocket ID, then retry a mutating
      admin action **without logging out**. It should fail immediately; that's
      the userinfo re-check working.
- [ ] `python3 console/reconciler/reconcile.py --dry-run` runs clean (needs
      `pip3 install --user pyyaml`).
- [ ] Confirm the reconciler refuses an `elevated`/`dangerous` registry entry
      that's enabled without `accepted_by`/`accepted_on`.

## Home Assistant (see home-assistant.md)

- [ ] HACS: install openai-compatible-conversation (or Extended OpenAI
      Conversation for function-calling device control).
- [ ] Wyoming integrations: STT 10300, TTS 10200, wake word 10400.
- [ ] MCP integration(s): memory `http://<mini>:8003/mcp` (+ Outline if
      desired). HA connects **unauthenticated** and gets the shared household
      identity — it cannot send a bearer token. See home-assistant.md.
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
