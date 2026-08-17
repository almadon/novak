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
what the AI "knows" in a normal wiki. Outline **serves MCP itself** at
`https://et.a64.one/mcp` — no wrapper container — giving every model and
client the same search/read (and optionally write) tools. Prefer this over an
opaque vector store for anything you'd want to audit, and prefer a service's
native MCP endpoint over wrapping it whenever one exists.

### Memory — Mem0 self-hosted, fronted by memory-mcp

Accumulated per-user facts (preferences, people, ongoing context). Runs
locally on Postgres/pgvector.

This layer was rebuilt because **OpenMemory was deprecated and sunset
upstream**. Its replacement, the unified Mem0 self-hosted server, is
multi-user (`user_id` per request, per-user API keys) but **REST-only** — and
MCP is what lets HA and Open WebUI share one store. So a small first-party
shim, [novak-integracje/memory-mcp/](https://github.com/almadon/novak-integracje/blob/HEAD/memory-mcp/README.md), exposes Mem0 over MCP and
injects the caller's `user_id` from a bearer token. The caller cannot name a
user; that is what keeps one person's memories out of another's context, and
what stops a prompt-injected document from asking the model to read someone
else's history.

The console (not the shim) is the inspect/edit surface — it authenticates via
Pocket ID and calls Mem0's REST API directly. Do not rely on Open WebUI's
built-in Memory feature for anything important; it is siloed inside Open WebUI.

Backend choice is deliberately replaceable: the Mem0-specific code is confined
to [memory-mcp/src/mem0.ts](https://github.com/almadon/novak-integracje/blob/HEAD/memory-mcp/src/mem0.ts). Identity resolution
and the MCP surface are backend-agnostic, so swapping memory engines means
rewriting one file, not the integration.

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
WebUI → MCP servers → Outline/Vikunja/memory-mcp.

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

## Placement — this stack is distributed, not single-host

`docker-compose.yml` was written assuming everything runs on the mini beside
oMLX (hence `host.docker.internal`). That is not the deployment: Open WebUI
already runs on a separate VPS. Placement now has to be decided per service,
the same pinned-vs-replicated reasoning used for the proxy/DNS config.

What constrains each piece:

| Service | Constraint | Where |
|---|---|---|
| oMLX | Metal/MLX — cannot be containerized or moved | mini, mandatory |
| Mem0 + Postgres | **every memory write triggers LLM extraction calls** — wants to be next to oMLX, or each write pays a round trip | with oMLX |
| memory-mcp | thin; follows Mem0 | with Mem0 |
| Wyoming STT/TTS | voice latency budget is ~1–2s end to end; keep close to HA and the satellites | with HA |
| Open WebUI | just a frontend; only needs to reach oMLX | already on VPS |
| Console | reaches Mem0 often, Pocket ID once per session | with Mem0 (decided) |

The console runs beside Mem0 for data locality. The accepted cost: **Pocket ID
is on a VPS, so a WAN outage prevents logging in to a console that is otherwise
entirely local.** Existing sessions survive (8h JWT), so a brief outage is not
locking. If that becomes annoying, the fix is a break-glass path, not moving
the console — moving it just relocates the problem onto every memory read.

### Reachability

Public ingress lives on the VPS; the home network forwards nothing.

```
   internet ──▶ Caddy (VPS) ──▶ Open WebUI (VPS)
                                     │
                                     │  Tailscale
                                     ▼
                          oMLX · Mem0 · memory-mcp · Konzol   (Mac, home)
                                     ▲
                          Wyoming voice ── HA + satellites    (LAN)
```

Exposure is a per-service decision recorded in [decisions.md](decisions.md)
#15. The rule: a service faces the internet only if it was built to — Open
WebUI has accounts and sessions and expects strangers; oMLX and memory-mcp
assume every caller is friendly, so they stay on Tailscale.

Two consequences worth being explicit about:

- **Open WebUI depends on the WAN link to think.** With oMLX at one site and
  Open WebUI at another, chat stops working when the link does. Voice through
  HA, if HA and oMLX are co-located, keeps working. That is an argument for
  treating voice as the more reliable interface, not the more fragile one.
- **Prompt content transits whichever host runs the frontend.** That host sees
  plaintext. This is consistent with the threat model — the concern is a public
  *model vendor*, and a VPS you control is not one — but it does mean the VPS
  is now in scope for the same care as the mini.

## Ports

| Service | Port |
|---|---|
| oMLX | per app config (`OMLX_PORT`) |
| Open WebUI | 3000 |
| Outline MCP | external — `https://et.a64.one/mcp` |
| Vikunja MCP | 8002 |
| Mem0 (REST) | 8765 |
| memory-mcp (MCP) | 8003 |
| Console | 3002 |
| Wyoming whisper (STT) | 10300 |
| Wyoming piper (TTS) | 10200 |
| Wyoming openWakeWord | 10400 |

All LAN-only. For remote access use Tailscale; never port-forward.
