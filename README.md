# Novak — private LLM stack for the Mac mini M4 (24GB)

A self-hosted, model-switching AI hub built around **oMLX** for inference, with
**Open WebUI** for text/voice chat, **MCP servers** as the plugin system
(Outline, Vikunja, shared memory, and future integrations), and **Home
Assistant / HA Voice** as a peer client of the same services.

Design principle: **the hub is a services layer, not a frontend.** Every
client (Open WebUI, HA Assist, future CLIs/apps) talks to the same inference
server and the same MCP tools. Nothing important lives inside any single UI.

```
                     ┌─ Open WebUI (text + voice chat, per-user accounts)
  clients            ├─ HA Assist / HA Voice (official MCP client integration)
                     └─ future clients
                           │
  shared services    ├─ oMLX ──────────── stateless inference, model switching
  (the hub)          ├─ OpenMemory MCP ── per-user long-term memory (mem0)
                     ├─ Outline MCP ───── canonical knowledgebase
                     ├─ Vikunja MCP ───── tasks
                     └─ Wyoming STT/TTS ─ whisper + piper for HA Voice
```

## Deploying on the mini

1. Get this repo onto the mini (AirDrop, rsync, or push to a private remote
   and clone).
2. Run the bootstrap:

   ```bash
   ./scripts/bootstrap.sh
   ```

   It installs Homebrew (if missing), OrbStack, and oMLX, applies 24/7 power
   settings, and brings up the Docker stack.
3. Work through [docs/deploy-checklist.md](docs/deploy-checklist.md) — it
   lists every item that could not be verified off-host (ports, image tags,
   flag names) and the one-time manual steps (model downloads, HA setup,
   secrets).

## Repo map

| Path | What it is |
|---|---|
| [docker-compose.yml](docker-compose.yml) | Open WebUI, MCP servers, OpenMemory, Wyoming voice services |
| [.env.example](.env.example) | Non-secret configuration; copy to `.env` |
| [scripts/bootstrap.sh](scripts/bootstrap.sh) | One-shot host setup |
| [scripts/up.sh](scripts/up.sh) | Starts the stack; pulls secrets from macOS Keychain |
| [scripts/power.sh](scripts/power.sh) | pmset settings for 24/7 operation |
| [omlx/SETTINGS.md](omlx/SETTINGS.md) | oMLX configuration: models, memory limits, TTLs, profiles |
| [docs/architecture.md](docs/architecture.md) | Full architecture and rationale |
| [docs/security.md](docs/security.md) | Secrets handling, least privilege, prompt-injection guardrails |
| [docs/home-assistant.md](docs/home-assistant.md) | HA + HA Voice wiring (conversation agent, MCP, Wyoming) |
| [docs/deploy-checklist.md](docs/deploy-checklist.md) | On-host verification checklist |

## Non-goals

- No custom web frontend. New capabilities are added as MCP servers, which
  every client picks up. Build UI only for things chat can't express, and
  build it as a view over these same services.
- No cloud model fallback. If a feature needs a cloud API, it gets its own
  MCP server with its own scoped key — the chat model never sees credentials.
