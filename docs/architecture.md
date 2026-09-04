# Architecture

## Principle

The hub is a **services layer**, not a frontend. Models are stateless;
memory, knowledge, and tools live in standalone services that every client
consumes. Open WebUI is *a* client, not *the* system — if it disappeared
tomorrow, nothing of value would be lost.

## Layers

### Inference — pluggable engines behind the router

Not one fixed backend: any engine that speaks an OpenAI-compatible
`/v1/chat/completions` is a valid Novak inference engine, chosen per
deployment (or per model role — nothing stops mixing engines). See
decision #28 and [engines.md](engines.md) for the full reasoning and the
current options. Two are documented today:

- **oMLX** — native macOS app (Metal/MLX can't run in a Linux container),
  multi-model serving with switching, continuous batching, SSD-tiered KV
  cache. Profiles present one loaded model as several virtual models
  (`ha-voice`, `chat`, `deep`) with different settings at zero RAM cost.
  See [omlx-settings.md](omlx-settings.md) for the tuning reasoning.
- **Ollama** — ordinary Linux container, GPU passthrough via
  `--device=/dev/dri`, no vendor plugin needed for AMD. Vulkan
  (`OLLAMA_VULKAN=1`) beats ROCm on RDNA4 specifically. Native
  `OLLAMA_MAX_LOADED_MODELS`/`OLLAMA_NUM_PARALLEL` give the same
  multi-model/multi-user behavior oMLX's profiles do.

Everything else in this stack (Hindsight, Open WebUI, the console, voice)
is plain Docker Compose with no platform assumption baked in — inference
was always the only piece that needed a specific host, and now that's
explicit rather than assumed.

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

**Decision 21's routing layer exists now** ([router/](../router/), decision
#23): LiteLLM in front of oMLX, injecting the persona from `prompts/` into
every request for `chat`, `deep`, and `ha-voice`, transparently — no
per-client config, no copy to keep in sync. A client switches to it by
pointing its base URL at the router's port instead of oMLX's; nothing else
changes, since the model names are the same either way.

**This is half of decision 21, not all of it.** "A verified user identity
can travel with the request, which is what makes per-user behaviour
possible" — that part is not built. The router injects a persona and does
nothing else; it does not read, forward, or act on who is calling. Memory
scoping is unaffected either way, since it was never routed through here —
Hindsight's own per-connection URL scoping is what does that, unchanged.

The router is optional, gated behind its own compose profile
(`docker-compose.yml`), so a client can still be pointed at oMLX directly.
Nothing currently checks whether one is — that's the persona drift check
decision #21 named as the prerequisite for trusting this at all, and it
still doesn't exist (see [STATE.md](STATE.md)).

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
| [`registry/omlx.yaml`](../registry/omlx.yaml) | which models exist, and what profiles they expose | [`reconciler/omlx_apply.py`](../reconciler/omlx_apply.py) → oMLX's JSON files |
| [`prompts/`](../prompts/novak-chat.md) | the assistant's personas | [`router/persona_hook.py`](../router/persona_hook.py) → every request, if a client points at the router (decision #23); each client's own config otherwise |

**`registry/omlx.yaml`** is [`docs/omlx-settings.md`](omlx-settings.md) reduced to
values a machine can apply and re-check. settings.md holds the reasoning — why
the 4B is always resident, why nothing 30B-class fits in 24GB; the YAML holds
the numbers. Read one to decide, edit the other to apply. Idle TTL sits per
model rather than per profile because oMLX stores it that way.

It is applied by writing oMLX's own JSON files, not through its admin API,
because that API needs a second credential the reconciler would have to hold —
see decision 17.

**Both of the last two are built now.** This paragraph used to say neither
was — recorded here, not deleted, since the reasoning that led to writing
them down before anything existed is still worth keeping.

### The gap this leaves

The registry ends up in one place — compose — so drift is impossible; the file
*is* the state.

Prompts had the opposite property, and for any client still pointed at oMLX
directly, still do: Open WebUI keeps system prompts in its database and
Home Assistant keeps them in its config entry, so each persona exists as a
copy that was pushed there, editable in place without the repo knowing.

**A client pointed at the router instead doesn't have this problem** — it
never holds a copy to drift, since `router/persona_hook.py` reads
`prompts/` fresh on every request. What remains open is knowing which
state any given client is actually in. Nothing currently checks whether a
client has been switched over or is still talking to oMLX directly with
whatever persona (or none) its own config holds — that's the persona
drift check decision 21 named as the prerequisite for trusting the router
at all, and it still doesn't exist. See [STATE.md](STATE.md).

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

## Placement — Spire is the primary, sole-host deployment

**Corrected 2026-09-04, superseding the previous correction below.** The
migration decision #28 recorded is now complete, not aspirational:
Hindsight, Open WebUI, the console, the Wyoming voice services, and Ollama
all run together on Spire (Unraid, AMD RDNA4 GPU). Mitochon (the Mac mini)
has been taken down as a server and is kept only for oMLX development —
Novak's household deployment has no dependency on it running.

`docker-compose.yml` reflects this: it is one file supporting both host
shapes (oMLX-on-host for Apple Silicon, the in-stack `ollama` service
behind its own compose profile for Linux+GPU), not a file written for one
specific machine (decision #33). Storage also split on Spire per decision
#33: compose manifests and `.env` stay under Unraid's appdata path (where
Compose Manager expects them); databases, media, and model weights live
under `/mnt/teracache/Novak/{data,models,config}` on bulk storage instead.

See [engines.md](engines.md) for the inference-engine side of this, and
[ollama-settings.md](ollama-settings.md) for what's actually running.

*(Previous correction, 2026-08-27: this section once said Open WebUI runs on
a separate VPS — true of an earlier plan, not true of any deployment shape
described above.)* The reverse proxy fronting the portal and Open WebUI
remains a separate Caddy instance on a LAN-neighboring machine — see
[proxy.md](proxy.md).

What constrains each piece, now that everything but oMLX is co-located on
one host:

| Service | Constraint | Where |
|---|---|---|
| oMLX | Metal/MLX — cannot be containerized or moved | Mitochon, kept for development only, not depended on in production |
| Ollama | needs a GPU worth using | Spire (RDNA4/Vulkan) — the household's real `deep`/`chat`/`ha-voice` engine now |
| Hindsight | every memory write triggers an LLM extraction call — wants to be next to whichever engine serves it | Spire, pointed at Spire's own Ollama (`HINDSIGHT_LLM_MODEL`/`HINDSIGHT_LLM_PROVIDER`), not oMLX |
| Wyoming STT/TTS | voice latency budget is ~1–2s end to end; keep close to HA and the satellites | Spire, same LAN as HA |
| Open WebUI | just a frontend; reaches whichever engine(s) the router points at | Spire |
| Console | reaches Hindsight often, Pocket ID once per session | Spire, with Hindsight |

The console runs beside Hindsight for data locality. The accepted cost: **Pocket ID
is on a VPS, so a WAN outage prevents logging in to a console that is otherwise
entirely local.** Existing sessions survive (8h JWT), so a brief outage is not
locking. If that becomes annoying, the fix is a break-glass path, not moving
the console — moving it just relocates the problem onto every memory read.

### Reachability

**VERIFY before treating this as settled:** the diagram below and decision
#15's public/private exposure model were both written assuming Open WebUI
sits behind a VPS Caddy that terminates public internet traffic. That VPS
placement was corrected above; whether the LAN-neighboring Caddy mentioned
there *also* takes that public-facing role, or whether this deployment is
LAN/tailnet-only for now with no public exposure at all, has not been
confirmed. Decision #15's reasoning about what may and may not face the
internet is unaffected either way — only the physical location of the
proxy doing it is in question here.

```
   [public internet, if this deployment has any — see the VERIFY above]
                                     │
                                     ▼
                     Caddy (LAN-neighboring host, not this Mac)
                                     │
                                     ▼
                          Open WebUI    (this Mac, same host as oMLX)
                                     │
                                     ▼
                          oMLX · Hindsight · Konzol   (this Mac)
                                     ▲
                          Wyoming voice ── HA + satellites    (LAN)

   LAN / tailnet ──▶ Portal's own Caddy ──▶ TinyAuth ──▶ Open WebUI, Konzol
                      (Mac, home — decision #22; not the VPS Caddy above,
                       and not public — see docs/proxy.md)
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
