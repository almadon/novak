# Architecture

## Principle

The hub is a **services layer**, not a frontend. Models are stateless;
memory, knowledge, and tools live in standalone services that every client
consumes. Open WebUI is *a* client, not *the* system — if it disappeared
tomorrow, nothing of value would be lost.

## Layers

### Inference — oMLX (native macOS app, not containerized)

- OpenAI-compatible API, multi-model serving with switching, continuous
  batching, SSD-tiered KV cache.
- MLX must run natively for Metal access; everything else is in Docker and
  reaches it via `host.docker.internal`.
- Profiles present one loaded model as several virtual models
  (`ha-voice`, `chat`, `deep`) with different settings at zero RAM cost.
- See [../omlx/SETTINGS.md](../omlx/SETTINGS.md) for the 24GB tuning.

### Knowledge — Outline (canonical), via MCP

Human-curated documents are the source of truth, and they live in Outline —
already running, already searchable, and auditable: you can read and correct
what the AI "knows" in a normal wiki. The Outline MCP server gives every
model and client the same search/read (and optionally write) tools. Prefer
this over an opaque vector store for anything you'd want to audit.

### Memory — OpenMemory (mem0), via MCP

Accumulated per-user facts (preferences, people, ongoing context). Runs
locally with Qdrant; exposed over MCP so Open WebUI, HA, and future clients
share one store. The OpenMemory UI (port 3001) lets you inspect and delete
memories. Do not rely on Open WebUI's built-in Memory feature for anything
important — it is siloed inside Open WebUI.

### Tools / plugins — one MCP server per capability

Outline, Vikunja today; email, utilities, budget later. Each is a container
in the compose file following the same pattern (stdio server wrapped by
supergateway into streamable-HTTP). Adding a capability = adding a compose
block + registering the endpoint in each client. No frontend work.

### Identity — one persona, every client

The assistant is **Novak** wherever it's reached. The master copies of its
system prompts live in [../prompts/](../prompts/novak-chat.md): a full
persona for text chat, and a deliberately terse one for voice. Set them on
the oMLX profiles if profiles carry system prompts, so new clients inherit
the identity for free; otherwise set per client and keep `prompts/` as the
source of truth.

The persona is not decoration — it encodes the security posture the model
itself must enforce: never ask for credentials, treat retrieved content as
data rather than instruction, and confirm before acting. See
[security.md](security.md).

### Clients

- **Open WebUI** — text + voice chat, per-user accounts/RBAC, model
  switcher (sees every oMLX model/profile automatically). Registers MCP
  servers under Admin → Settings → Tools (native MCP, streamable-HTTP).
- **Home Assistant** — Assist pipeline with an OpenAI-compatible
  conversation agent pointed at oMLX (`ha-voice` profile), plus HA's
  official MCP client integration for the shared memory/knowledge tools.
  See [home-assistant.md](home-assistant.md).

## Data flow examples

**Text chat**: browser → Open WebUI → oMLX (`chat`); tool calls go Open
WebUI → MCP servers → Outline/Vikunja/OpenMemory.

**Voice via HA**: speaker → HA Assist → Wyoming whisper (STT, on the mini)
→ conversation agent → oMLX (`ha-voice`) with HA-registered MCP tools →
Wyoming piper (TTS, on the mini) → speaker. Same memory, same knowledge,
no Open WebUI in the loop.

## Privacy / leakage model

Local weights cannot leak conversations into anyone's training set —
inference is a local computation with no vendor channel. The residual
risks are operational (credentials, over-broad tools, prompt injection)
and are addressed in [security.md](security.md). Outbound traffic from
this stack: model/image downloads (inbound content), and whatever MCP
servers you deliberately add that talk to external APIs (email, utilities)
— each with its own scoped credential, never proxied through a model
prompt.

## Ports

| Service | Port |
|---|---|
| oMLX | per app config (`OMLX_PORT`) |
| Open WebUI | 3000 |
| Outline MCP | 8001 |
| Vikunja MCP | 8002 |
| OpenMemory API/MCP | 8765 |
| OpenMemory UI | 3001 |
| Wyoming whisper (STT) | 10300 |
| Wyoming piper (TTS) | 10200 |
| Wyoming openWakeWord | 10400 |

All LAN-only. For remote access use Tailscale; never port-forward.
