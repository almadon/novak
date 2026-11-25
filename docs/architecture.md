# Architecture

How the pieces fit, and why each one sits where it does. The reasoning for each choice is in [decisions.md](decisions.md), and what is true on the running system today is in [STATE.md](STATE.md).

<p align="center">
  <img src="images/architecture.svg" alt="Clients talk to a services layer made of a router in front of the inference engine, and a gateway that knows who is asking. The gateway reaches memory, notes, tasks, the house and search over MCP. The console reads status from the gateway and sends it change requests." width="100%">
</p>

## Principle

The hub is a **services layer**, not a frontend. Models are stateless. Memory, knowledge and tools live in standalone services that every client uses. Open WebUI is one client among several, and if it disappeared nothing of value would be lost.

## The layers

### Inference: pluggable engines behind a router

Any engine that speaks an OpenAI-compatible `/v1/chat/completions` can be a Novak engine, chosen per deployment, or even per model role (decision #28, [engines.md](engines.md)). Two are documented:

- **Ollama** is an ordinary Linux container with GPU passthrough (`--device=/dev/dri`) and no vendor plugin for AMD. Vulkan (`OLLAMA_VULKAN=1`) beats ROCm on RDNA4. It is what the household runs. See [ollama-settings.md](ollama-settings.md).
- **oMLX** is a native macOS app, because Metal and MLX cannot run in a Linux container. Profiles present one loaded model as several virtual ones (`ha-voice`, `chat`, `deep`) with different settings at no extra memory cost. See [omlx-settings.md](omlx-settings.md).

The router (LiteLLM, [router/](../router/)) sits in front of the engine. It injects the persona from `prompts/` into every request for `chat`, `deep` and `ha-voice`, so no client has a copy to keep in sync (decision #23), and clients see model names, not engines. It has its own key. A client can still talk to the engine directly, in which case nothing checks what persona it sends.

Everything else in the stack is plain Docker Compose with no platform assumption. Inference was always the only piece that needed a particular host.

### Knowledge: Outline, over MCP

Documents a human curates are the source of truth, and they live in Outline, which is a normal wiki you can read and correct. Outline serves MCP itself, so there is no wrapper. Prefer this over an opaque vector store for anything you want to audit, and prefer a service's native MCP endpoint over wrapping it whenever one exists.

### Memory: Hindsight

Hindsight holds per-person facts (preferences, people, ongoing context) in **banks**, with Postgres embedded in the image so it is one container. It speaks MCP at `/mcp/<bank>/`, and each connection is scoped to one bank by its URL. The tools take no bank argument, so a model has nowhere to name someone else's memories. This replaced a Mem0-plus-shim arrangement: the shim existed to add MCP and enforce that scoping, Hindsight does both, and about 400 lines of first-party code were deleted. See [how-memory-works.md](how-memory-works.md) and [memory-setup.md](memory-setup.md).

Do not rely on Open WebUI's built-in Memory feature for anything important. It is siloed inside Open WebUI.

### Tools: one MCP server per capability, behind the gateway

Each capability (notes, tasks, the house, search) is its own MCP server, catalogued in [`registry/mcp-servers.yaml`](../registry/mcp-servers.yaml) with a risk level. A service that already speaks MCP is listed as an external entry and needs no code. Adding a capability means adding a registry entry and, if needed, a compose block, with no frontend work.

The **gateway** ([gateway.md](gateway.md), decisions #58 and after) is the one MCP endpoint clients connect to. It knows who is asking from the connection, gives each person only their own tools with their own credentials, trims each connection's tool list to a short allowlist, holds removals until that person approves on their phone, and logs every call by argument name and never value. It is optional, and the registry can still be applied without it.

### Identity: one persona, and one person per connection

The assistant is **Novak** wherever it is reached. The persona encodes the security posture the model itself must enforce: never ask for credentials, treat retrieved content as data and confirm before acting ([security.md](security.md)). Who is asking is a separate question, answered by the gateway rather than the router. The router injects a persona and does not act on the caller. See [identity.md](identity.md).

### Clients

- **Open WebUI** is text chat with per-person accounts and a model switcher. It signs in through Pocket ID only (decision #68), and its gateway connections and presets are declared in `registry/openwebui.yaml` (decisions #66 and #67).
- **Home Assistant** runs the voice pipeline: one pipeline and agent per person, HA's own Whisper and Piper add-ons for speech, and its `litellm` conversation agent pointed at the router. See [home-assistant.md](home-assistant.md).
- **Coding agents**, such as Pi, can use the router ([pi.md](pi.md)).
- **Konzol, the console**, is described next.

### The console

Konzol ([console/](../console/README.md)) is a web view over the stack, and it is optional. It reads status from the gateway with one key and sends the gateway change requests with another, and it reads memories from Hindsight on the server. It never talks to Docker, never decides an approval and never calls a tool for you. When it asks for a change, the gateway sends Approve and Deny to that person's phone through Supernotify, and nothing happens until they approve (decisions #64, #72 and #79). It signs people in through Pocket ID and maps each to their own bank.

## Configuration as data

Three declarative inputs live in this repository, and each is applied by something simple instead of being typed into a web page. A file in git is validated strictly, applied idempotently, and git is the audit log.

| File | Declares | Applied by |
|---|---|---|
| [`registry/mcp-servers.yaml`](../registry/mcp-servers.yaml) | Which MCP servers exist and how risky each is | [`reconciler/reconcile.py`](../reconciler/reconcile.py), into compose |
| [`registry/omlx.yaml`](../registry/omlx.yaml) | Which models exist and what profiles they expose | [`reconciler/omlx_apply.py`](../reconciler/omlx_apply.py), into oMLX's own JSON files |
| [`prompts/`](../prompts/novak-chat.md) | The assistant's personas | [`router/persona_hook.py`](../router/persona_hook.py), on every request through the router |

`registry/omlx.yaml` is [omlx-settings.md](omlx-settings.md) reduced to values a machine can apply and re-check. The settings page holds the reasoning and the YAML holds the numbers. It is applied by writing oMLX's own JSON files and not through its admin API, because that API needs a second credential the reconciler would otherwise have to hold (decision #17).

### The gap this leaves

The registry ends up in one place, compose, so it cannot drift. Prompts are different for any client still pointed at the engine directly. Open WebUI keeps system prompts in its database and Home Assistant keeps them in its config, so each persona exists as a pushed copy that can be edited in place without the repo knowing. A client pointed at the router has no copy to drift. Decision #44 added a log line that fires when a router-bound client silently sends its own system message, shown by `novak drift --live`. What has no detector is whether a client is pointed at the router at all. See [STATE.md](STATE.md).

## Data flow examples

**Text chat:** browser, Open WebUI, router, engine (`chat`). Tool calls go from Open WebUI to the gateway, then to the MCP servers.

**Voice through Home Assistant:** speaker, HA Assist, HA's own Whisper add-on for speech to text (decision #39), HA's `litellm` conversation agent (decision #42), the router, the engine (`ha-voice`) with HA's own Assist API for device control, HA's Piper add-on for text to speech, speaker. Wake word detection is the one voice piece Novak still serves, through `openwakeword` over Wyoming.

**A removal that needs a yes:** a client asks for a removal through the gateway, the gateway holds the call and sends Approve and Deny to the person's phone, a button press becomes a Home Assistant event, and the gateway runs the call only after it sees Approve. An unanswered request expires and changes nothing.

## Privacy and leakage

Local weights cannot leak conversations into someone's training set, because inference is a local computation with no vendor channel. The remaining risks are operational (credentials, over-broad tools, prompt injection) and are covered in [security.md](security.md). Outbound traffic is model and image downloads, plus whatever MCP servers you deliberately add that call external APIs, each with its own scoped credential that is never passed through a prompt.

## Placement

**Spire (Unraid, AMD RDNA4) is the sole production host** (decisions #28 and #33). Hindsight, Open WebUI, the console, the gateway, the router, `openwakeword` and Ollama all run on it together. Home Assistant runs on its own host. The original macOS host is no longer a server and is kept for oMLX development, so the household has no dependency on it.

`docker-compose.yml` supports both host shapes in one file: oMLX on the host for Apple Silicon, or the in-stack `ollama` service behind its own profile for Linux with a GPU. Compose manifests and config stay under Unraid's appdata path, where Compose Manager expects them. Databases, media and model weights live on bulk storage under `/mnt/teracache/Novak/{data,models,config}`.

| Service | Constraint | Where |
|---|---|---|
| oMLX | Metal and MLX, so it cannot be containerised or moved | A macOS host, kept for development |
| Ollama | Needs a GPU worth using | Spire |
| Hindsight | Every memory write triggers an LLM extraction call, so it wants to sit next to the engine | Spire, pointed at Spire's own Ollama |
| `openwakeword` | Voice latency budget of about one to two seconds end to end, so it stays close to HA and the satellites | Spire, same LAN as HA |
| Open WebUI | A frontend that reaches whichever engine the router points at | Spire |
| Console | Reaches Hindsight often and Pocket ID once per session | Spire, with Hindsight |

The console sits beside Hindsight for data locality. The accepted cost is that Pocket ID is on a VPS, so a WAN outage stops anyone logging in to an otherwise local console. Existing sessions survive (an eight-hour token), so a short outage does not lock anyone out. If it becomes annoying, the fix is a break-glass sign-in, not moving the console.

### Reachability

Exposure is a per-service decision recorded in decision #15. A service faces the internet only if it was built to: Open WebUI has accounts and sessions and expects strangers, while the engine, Hindsight, the gateway and the console assume friendly callers and stay on the tailnet. The full table is in [security.md](security.md).

Two things follow from putting the frontend behind a proxy on another host:

- **Open WebUI then depends on the link to think.** Voice through Home Assistant, which is on the same network as the engine, keeps working when the link is down, which is an argument for treating voice as the more reliable interface.
- **Prompt content transits the proxy host in plain text.** That fits the threat model, since the concern is a public model vendor and a proxy you run is not one, but it puts that host in scope for the same care as the stack's own.

**VERIFY:** whether the LAN-side Caddy ([proxy.md](proxy.md)) also takes a public-facing role for Open WebUI, or this deployment is tailnet-only with no public exposure, has not been confirmed. Decision #15's reasoning holds either way. Only the proxy's physical location is in question.

## Ports

External ports are Spire's, in the `134xx` range by convention (decision #33). Each has an override in `.env`.

| Service | Port |
|---|---|
| Ollama | `11434` (`OLLAMA_PORT`) |
| Router (LiteLLM) | `13402` (`ROUTER_PORT`) |
| Open WebUI | `13400` (`OPENWEBUI_PORT`) |
| Console | `13401` (`CONSOLE_PORT`) |
| Hindsight API and MCP | `13403` (`HINDSIGHT_PORT`), on `127.0.0.1` only (decision #62) |
| Hindsight web UI | `13404` (`HINDSIGHT_UI_PORT`), on `127.0.0.1` by default |
| Wyoming openWakeWord | `13407` (`OPENWAKEWORD_PORT`) |
| Persona server, which HA pulls | `13408` (`PERSONA_PORT`, `PERSONA_BIND`) |
| Ingest (optional) | `13409` (`INGEST_PORT`, `INGEST_BIND`), see [ingest.md](ingest.md) |
| Gateway (optional) | `13410` (`GATEWAY_PORT`, `GATEWAY_BIND`), see [gateway.md](gateway.md) |
| oMLX | Set in its own app config (`OMLX_PORT`), on the macOS development host |
| Outline and Tududi | External services, reached by their own addresses |

The portal profile's reverse proxy also defaults to `13408` (`PORTAL_PORT`), the same as the persona server, so set one of them if you run both (VERIFY: read from `docker-compose.yml`, not run).

The router, Ollama, the persona server, ingest and the gateway take a `*_BIND` address. Set each to the host's Tailscale IP so only the tailnet reaches it (decision #54). Containers in the stack reach each other by service name and never through these published ports. Speech to text and text to speech are no longer Novak ports (decision #39), because they are Home Assistant's own add-ons.

Everything here is LAN or tailnet only. For remote access use Tailscale, and never port-forward. oMLX ships bound to `127.0.0.1`, so nothing off its machine reaches it until `server.host` is changed in its own settings. Containers still can, because OrbStack forwards loopback through `host.docker.internal`, which is why the stack can work while the oMLX row in `novak ports` shows no Tailscale reachability. See [proxy.md](proxy.md) before putting a proxy in front of it.
