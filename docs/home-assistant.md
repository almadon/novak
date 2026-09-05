# Home Assistant + HA Voice wiring

HA stays wherever it runs today, wired to Novak over the network: the
conversation agent talks to the router or an engine directly (decision
#28), STT/TTS are Home Assistant's own native Whisper/Piper add-ons
(decision #39 — no longer Novak's own containers), and MCP gives it tools.
This household's own real setup (Spire) is the reference: HA runs on
separate hardware (a Home Assistant Yellow), reaching Spire's router over
the LAN/tailnet.

## 1. Conversation agent → the router (or an engine directly)

HA's stock OpenAI integration still doesn't accept a custom base URL
([core#137087](https://github.com/home-assistant/core/issues/137087)), so this
needs a custom component. Install **Custom Conversation** via HACS
(<https://github.com/michelle-avery/custom-conversation>).

It lets you keep HA's built-in Assist API for device control, which is what
this stack wants: the conversation agent handles *language*, and tools arrive
through HA's MCP integration (§3) or through the "Assist" API choice built
into Custom Conversation itself (used here — see below). It can also run
both — built-in intents first, the LLM for whatever they don't match.

Configure it as the **OpenAI** provider and override the base URL — its
[supported providers](https://github.com/michelle-avery/custom-conversation/blob/main/docs/supported-providers.md)
doc confirms that is how arbitrary self-hosted endpoints are meant to be used,
while warning that *"supposedly 'OpenAI-compatible' APIs are sometimes not
fully compatible."* Confirmed directly against this household's real router
(decision #40): it works, once past two real compatibility bugs — see below.

> **If you are following an older copy of these notes**, they recommended
> `openai-compatible-conversation`. Its maintainer has since disclaimed it —
> *"I personally cannot support this, as I don't actually use this
> integration"* — and points at Custom Conversation, which is the same author
> and actively maintained. See decision 19 for the full comparison, including
> when Extended OpenAI Conversation is the better answer.

Settings (real values, this household — adjust host/port to yours):

- Base URL: `http://<engine-host-ts-ip>:<ROUTER_PORT>/v1` (`13402` by
  default) if going through the router — recommended, since it's what
  injects Novak's persona (decision #21) — or a specific engine's own
  base URL to bypass the router entirely.
- API key: the router's shared key (`OMLX_API_KEY`), or the engine's own
  if going direct.
- Model: the router's short role name, e.g. **`ha-voice`** — not an
  engine's own long model id. The router exposes role names directly;
  only a direct-to-engine setup needs the engine's own naming (oMLX:
  `Qwen3-4B-Instruct-2507-4bit:ha-voice`; Ollama: a plain tag like
  `qwen3:4b-instruct`).
- API choice: **Assist**, not "No control" — exposes HA's device-control
  intents to the LLM without a separate MCP round trip.

### Two real compatibility bugs found running this (decision #40)

Both against a recent Home Assistant Core (2026.9.0) with Custom
Conversation v1.6.1 — check whether they're already fixed upstream before
assuming you'll hit them:

1. **Missing `voluptuous-openapi` dependency.** The integration's
   `manifest.json` doesn't declare it despite importing it, so HA never
   installs it and the integration fails to load entirely
   (`ModuleNotFoundError`). Fix: add `"voluptuous-openapi"` to the
   `requirements` list in the installed
   `custom_components/custom_conversation/manifest.json` and restart HA
   Core — it'll get pip-installed on the next startup like any other
   declared requirement.
2. **Removed `llm.AssistAPI` class.** HA Core 2026.9.0 removed it; the
   integration's `config_flow.py` still references
   `llm.AssistAPI.IGNORE_INTENTS` in three places, crashing every config
   flow interaction with `AttributeError`. An open, unmerged upstream fix
   exists (PR #112 on the integration's repo) — applying it manually
   (replace each `llm.AssistAPI.IGNORE_INTENTS` reference with an empty
   list default) resolves it.

**A third, still-open bug** (upstream issue #71): a "thinking" model's
`reasoning_content` output makes the integration fail with "Last message
in chat log is not AssistantContent". Confirmed by testing directly: it's
model-dependent, not integration-version-dependent. Workaround that
avoids it entirely — use a non-thinking model variant for the `ha-voice`
role (e.g. Ollama's `qwen3:4b-instruct`, not the hybrid-thinking `qwen3:4b`
default) rather than waiting on an upstream fix.

**Also open, not yet root-caused**: Custom Conversation's own "Instructions
Prompt" field — where [prompts/novak-voice.md](../prompts/novak-voice.md)'s
persona is meant to go — is defined in the integration's code (a
`CONF_CUSTOM_PROMPTS_SECTION`) but doesn't render in the Options dialog on
this HA Core version. Confirmed it's not a scroll/viewport issue (checked
the live DOM directly). Until this is resolved, Custom Conversation
answers with its own generic assistant persona, not Novak's — everything
else (device control, real responses, no crashes) works.

## 2. STT/TTS: Home Assistant's own native add-ons

Decision #39: use HA's own Whisper and Piper add-ons (Settings → Add-ons
→ Store), not a separate Wyoming service Novak runs itself. Same
underlying models either way (`faster-whisper` at `auto`, Piper
`en_US-lessac-medium`), one less network hop between HA and the voice
services it needs fastest, and one less thing to keep in sync in two
places.

Wake word detection is the one piece that still comes from Novak's own
stack (`openwakeword`, Wyoming) — HA has no native equivalent for
server-side wake word on Wyoming satellites. Add it as a third Wyoming
Protocol integration pointing at `tcp://<core-host>:${OPENWAKEWORD_PORT}`
(`13407` by default).

## 3. Shared memory & knowledge via MCP

Settings → Devices & Services → Add Integration → **Model Context
Protocol** (official, HA 2025.2+), once per server:

- Hindsight: `http://<mini>:8888/mcp/household/` with the API key as a bearer
  token.

  **The bank is in the URL**, which is why this works at all: HA's MCP client
  cannot send custom headers per-server for scoping, so a backend that
  identified users by header could not be scoped for HA. The path solves it.

  **Register the `household` bank only.** Never a personal one — anyone who
  talks to a satellite would reach it, and a voice satellite cannot tell who is
  speaking. See docs/memory-setup.md.

Their tools become available to the conversation agent. **Keep the voice
agent's toolset small** — each tool call is a model round-trip and voice
should answer in ~1–2s. Memory + HA devices + Outline search is a good
ceiling; do not attach Vikunja/email/etc. to the voice pipeline.

## Wake word — "Hey Novak"

Read [wakeword.md](wakeword.md) first — it covers training the model
(synthetic, ~no effort) and one significant constraint: **HA Voice PE
hardware detects wake words on-device with microWakeWord, which has no
custom-training path**, so "Hey Novak" works for Wyoming satellites (like
Satellite1) but not (currently) for Voice PE. On Voice PE, keep a stock
trigger like "okay nabu" — the assistant still answers as Novak.

## 4. Assist pipeline

Settings → Voice assistants → Add assistant, named **Novak**:

- Conversation agent: Custom Conversation (→ `ha-voice`)
- STT: HA's native Whisper add-on, TTS: HA's native Piper add-on
- Wake word: `hey_novak` (satellites) or a stock word (Voice PE)
- Expose only the entities you actually want voice-controllable.

## Latency expectations

Whisper `faster-whisper` at `auto` STT ≈ well under a second for short
commands; the 4B model's first token is fast if the engine host has it
warm. If responses feel slow, check (in order): model role is really the
4B/`ha-voice` role, thinking mode is off (non-thinking model variant),
toolset size, whisper model size.
