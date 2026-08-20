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
- See [omlx-settings.md](omlx-settings.md) for the 24GB tuning.

### Knowledge — Outline (canonical), via MCP

Human-curated documents are the source of truth, and they live in Outline —
already running, already searchable, and auditable: you can read and correct
what the AI "knows" in a normal wiki. Outline **serves MCP itself** at
`https://et.a64.one/mcp` — no wrapper container — giving every model and
client the same search/read (and optionally write) tools. Prefer this over an
opaque vector store for anything you'd want to audit, and prefer a service's
native MCP endpoint over wrapping it whenever one exists.

### Memory — Hindsight

Accumulated per-user facts (preferences, people, ongoing context), stored in
**banks**. Postgres is embedded in the image, so it is one container.

Hindsight speaks MCP natively at `/mcp/<bank>/`, and each connection is scoped
to one bank by URL — the tools have no bank parameter. That is what keeps one
person's memories out of another's context, and out of reach of anything a
model reads: there is no argument in which to name someone else.

This replaced a Mem0-plus-shim arrangement. The shim existed to add MCP and to
enforce exactly that scoping; Hindsight does both, so ~400 lines of first-party
code were deleted. See [how-memory-works.md](how-memory-works.md) and
[memory-setup.md](memory-setup.md).

The console is the inspect/edit surface — it authenticates via Pocket ID and
maps each person to their bank. Do not rely on Open WebUI's built-in Memory
feature for anything important; it is siloed inside Open WebUI.

Backend choice stays replaceable, but the bar is now higher: any replacement
must bind identity to the connection rather than accept it as a parameter, or
the shim comes back.

### Tools / plugins — one MCP server per capability

Outline, Vikunja today; email, utilities, budget later. Each is a container
in the compose file following the same pattern (stdio server wrapped by
supergateway into streamable-HTTP). Adding a capability = adding a compose
block + registering the endpoint in each client. No frontend work.

### Identity — one persona, every client

The assistant is **Novak** wherever it's reached. The master copies of its
system prompts live in [../prompts/](../prompts/novak-chat.md): a full
persona for text chat, and a deliberately terse one for voice.

They are set **per client** today, because oMLX profiles have no system-prompt
field (decision 17) and no client will read one from a file (decision 18). Every
new client is another copy, maintained by hand.

That is a known gap, not the intended design. **Decision 21 puts a routing layer
in front of oMLX** so the persona is injected once, for every client, and so a
verified user identity can travel with the request — which is what makes
per-user behaviour possible at all. Per-client configuration cannot express it:
Open WebUI has one system prompt per model preset, shared by every user of it.

Until that exists, `prompts/` is the master copy and the copies will drift.

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

## Configuration as data

Three declarative inputs live in this repo, and each is applied by something
dumb rather than typed into a web UI. The pattern is the same every time: a
file in git, validated strictly, applied idempotently, with git as the audit
log.

| File | Declares | Applied by |
|---|---|---|
| [`registry/mcp-servers.yaml`](../registry/mcp-servers.yaml) | which MCP servers exist, and how risky each is | [`reconciler/reconcile.py`](../reconciler/reconcile.py) → compose |
| [`registry/omlx.yaml`](../registry/omlx.yaml) | which models exist, and what profiles they expose | *not built* → oMLX's JSON files |
| [`prompts/`](../prompts/novak-chat.md) | the assistant's personas | *not built* → each client's own config |

**`registry/omlx.yaml`** is [`docs/omlx-settings.md`](omlx-settings.md) reduced to
values a machine can apply and re-check. settings.md holds the reasoning — why
the 4B is always resident, why nothing 30B-class fits in 24GB; the YAML holds
the numbers. Read one to decide, edit the other to apply. Idle TTL sits per
model rather than per profile because oMLX stores it that way.

It is applied by writing oMLX's own JSON files, not through its admin API,
because that API needs a second credential the reconciler would have to hold —
see decision 17.

**Neither of the last two is built.** They are recorded so the shape is agreed
before anything writes to disk.

### The gap this leaves

The registry ends up in one place — compose — so drift is impossible; the file
*is* the state. Prompts do not have that property. **No client reads a prompt
from a file or from git.** Open WebUI keeps system prompts in its database and
Home Assistant keeps them in its config entry, so each persona exists as a copy
that was pushed there, and any of them can be edited in place without the repo
knowing.

That makes `prompts/` the master copy by convention rather than by mechanism,
which is a weaker guarantee than anything else here — and it matters, because
the persona carries part of the security posture (see decision 18 and
[security.md](security.md)).

Decision 21 closes this by moving the persona out of the clients entirely, into
a routing layer in front of oMLX. Until it exists, the gap stands.

## Data flow examples

**Text chat**: browser → Open WebUI → oMLX (`chat`); tool calls go Open
WebUI → MCP servers → Outline/Vikunja/Hindsight.

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
| Hindsight | **every memory write triggers an LLM extraction call** — wants to be next to oMLX, or each write pays a round trip | with oMLX |
| Wyoming STT/TTS | voice latency budget is ~1–2s end to end; keep close to HA and the satellites | with HA |
| Open WebUI | just a frontend; only needs to reach oMLX | already on VPS |
| Console | reaches Hindsight often, Pocket ID once per session | with Hindsight (decided) |

The console runs beside Hindsight for data locality. The accepted cost: **Pocket ID
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
                          oMLX · Hindsight · Konzol   (Mac, home)
                                     ▲
                          Wyoming voice ── HA + satellites    (LAN)
```

Exposure is a per-service decision recorded in [decisions.md](decisions.md)
#15. The rule: a service faces the internet only if it was built to — Open
WebUI has accounts and sessions and expects strangers; oMLX and Hindsight
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
| Hindsight (API + MCP) | 8888 |
| Hindsight (web UI) | 9999 |
| Console | 3002 |
| Wyoming whisper (STT) | 10300 |
| Wyoming piper (TTS) | 10200 |
| Wyoming openWakeWord | 10400 |

All LAN-only. For remote access use Tailscale; never port-forward.

The container ports above bind `0.0.0.0` and are reachable over the tailnet.
**oMLX is the exception:** it ships bound to `127.0.0.1`, so nothing off this
machine reaches it until `server.host` is changed in its own settings.
Containers still can, because OrbStack forwards loopback through
`host.docker.internal` — which is why the stack can work while the oMLX row in
`novak ports` shows no Tailscale reachability. See
[proxy.md](proxy.md) before putting a proxy in front of it.
