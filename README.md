# Novak — private LLM stack, centred on a Mac mini M4 (24GB)

A self-hosted, model-switching AI hub built around **oMLX** for inference, with
**Open WebUI** for text/voice chat, **MCP servers** as the plugin system
(Outline, Vikunja, shared memory, and future integrations), and **Home
Assistant / HA Voice** as a peer client of the same services.

Design principle: **the hub is a services layer, not a frontend.** Every
client (Open WebUI, HA Assist, the console, future CLIs/apps) talks to the same
inference server and the same MCP tools. Nothing important lives inside any
single UI.

```
                     ┌─ Open WebUI ───── text + voice chat        [on a VPS]
  clients            ├─ HA Assist ────── voice, MCP client integration
                     ├─ Console ──────── profiles, memories, MCP catalog
                     └─ future clients
                           │
  shared services    ├─ oMLX ──────────── inference, model switching  [mini]
  (the hub)          ├─ memory-mcp ────── per-user memory, over Mem0
                     ├─ Outline MCP ───── canonical knowledgebase
                     ├─ Vikunja MCP ───── tasks
                     └─ Wyoming STT/TTS ─ whisper + piper for HA Voice
```

Not everything runs in one place — see
[docs/architecture.md](docs/architecture.md) § Placement.

## Fresh install

> **Status: not yet deployed.** Nothing in this repo has been run on real
> hardware. Steps 1 and 2 below are known blockers that must be cleared first.
> Treat the whole checklist as unverified.

**Before the mini:**

1. **Generate lockfiles.** `console/` and `memory-mcp/` are built with
   `npm ci`, which needs a `package-lock.json` that does not exist yet. Without
   this the Docker build fails immediately:

   ```bash
   (cd console && npm install) && (cd memory-mcp && npm install)
   ```

   Commit both lockfiles. This is also what unblocks CI.

2. **Register an OIDC client in Pocket ID** for the console, with the `groups`
   scope enabled and a redirect URI per hostname you'll reach it by:
   `http://<host>:3002/api/auth/callback/pocketid`. Create an `admins.novak`
   group and put yourself in it — admin functions check for it.

**On the mini:**

3. Get this repo onto the mini (AirDrop, rsync, or push to a private remote
   and clone).
4. Put secrets in Keychain (see [docs/security.md](docs/security.md)).
   `scripts/up.sh` refuses to start if `CONSOLE_AUTH_SECRET`,
   `MEM0_POSTGRES_PASSWORD`, or `MEM0_JWT_SECRET` are still `changeme`.
5. Run the bootstrap:

   ```bash
   ./scripts/bootstrap.sh
   ```

   It installs Homebrew (if missing), OrbStack, and oMLX, applies 24/7 power
   settings, and brings up the Docker stack.
6. Work through [docs/deploy-checklist.md](docs/deploy-checklist.md) — it
   lists every item that could not be verified off-host (ports, image tags,
   flag names) and the one-time manual steps (model downloads, HA setup).

**Ordering wrinkle:** `MEM0_API_KEY` is *issued by* the Mem0 server on its
first start, but `memory-mcp` and the console need it to start. So the first
run is two passes: bring up `mem0` and `mem0-db`, take the key it issues, put
it in Keychain, then bring up the rest.

## Repo map

| Path | What it is |
|---|---|
| [docker-compose.yml](docker-compose.yml) | Open WebUI, Console, MCP servers, Mem0, Wyoming voice services |
| [console/](console/README.md) | Web console: profiles, memories, MCP catalog (Pocket ID OIDC) |
| [memory-mcp/](memory-mcp/README.md) | MCP front end for Mem0, with per-user scoping |
| [.env.example](.env.example) | Non-secret configuration; copy to `.env` |
| [scripts/bootstrap.sh](scripts/bootstrap.sh) | One-shot host setup |
| [scripts/up.sh](scripts/up.sh) | Starts the stack; pulls secrets from macOS Keychain |
| [scripts/power.sh](scripts/power.sh) | pmset settings for 24/7 operation |
| [omlx/SETTINGS.md](omlx/SETTINGS.md) | oMLX configuration: models, memory limits, TTLs, profiles |
| [prompts/](prompts/novak-chat.md) | Novak's persona — master copy of the chat and voice system prompts |
| [wakeword/](wakeword/README.md) | "Hey Novak" wake word: training, and the Voice PE caveat |
| [docs/architecture.md](docs/architecture.md) | Full architecture and rationale |
| [docs/decisions.md](docs/decisions.md) | Every decision made, why, and what it cost |
| [docs/credits.md](docs/credits.md) | Upstream projects, licences, what was evaluated |
| [docs/security.md](docs/security.md) | Secrets handling, least privilege, prompt-injection guardrails |
| [docs/home-assistant.md](docs/home-assistant.md) | HA + HA Voice wiring (conversation agent, MCP, Wyoming) |
| [docs/deploy-checklist.md](docs/deploy-checklist.md) | On-host verification checklist |

## Non-goals

- No custom web frontend *for chat*. New capabilities are added as MCP servers,
  which every client picks up. Build UI only for things chat can't express, and
  build it as a view over these same services.
  The [console](console/README.md) is that exception, not a violation: browsing
  memories, editing a persona, and managing plugins aren't things you can do by
  chatting. It owns no state that matters — if it vanished, nothing would be
  lost. See [docs/decisions.md](docs/decisions.md) #5.
- No cloud model fallback. If a feature needs a cloud API, it gets its own
  MCP server with its own scoped key — the chat model never sees credentials.
