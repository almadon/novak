# Home Assistant + HA Voice wiring

HA stays wherever it runs today, wired to Novak over the network: the
conversation agent talks to the router or an engine directly (decision
#28), STT/TTS are Home Assistant's own native Whisper/Piper add-ons
(decision #39 — no longer Novak's own containers), and MCP gives it tools.
This household's own real setup (Spire) is the reference: HA runs on
separate hardware (a Home Assistant Yellow), reaching Spire's router over
the LAN/tailnet.

## 1. Conversation agent → the router, via HA's native `litellm` integration

HA's stock OpenAI integration still doesn't accept a custom base URL
([core#137087](https://github.com/home-assistant/core/issues/137087),
closed as not planned), so pointing HA at Spire's router needs *something*
else. **Use HA Core's own native `litellm` integration** (added in HA Core
2026.8 — check Settings → Devices & Services → Add Integration → "LiteLLM"
before installing anything from HACS; if your HA predates 2026.8, see
decision #40/#41 for the HACS-based fallback this section used to
recommend).

It's built into Core, not a third-party dependency — no manifest/import
bugs to chase, no removed-API references to patch, none of decision #40's
entire bug class. It discovers every model the router exposes automatically
and creates one conversation agent per role name (`chat`, `ha-voice`,
`deep`, `task`), and it uses HA's own Assist API for device control — same
architecture this doc has always wanted (conversation agent handles
*language*, HA's own intents handle devices), just without a third party
in between.

Settings:

- URL: `http://<engine-host-ts-ip>:<ROUTER_PORT>` (`13402` by default) — no
  `/v1` suffix, no API key needed if the router doesn't enforce one.
- Per conversation agent (Settings → Devices & Services → LiteLLM → **Add
  conversation agent**): pick the role (**`ha-voice`** for this pipeline),
  paste [prompts/novak-voice.md](../prompts/novak-voice.md)'s persona into
  **Instructions** (supports Jinja templates), and check **Assist** under
  "Control Home Assistant."
- Wire the new agent into the actual pipeline: Settings → Voice assistants
  → your assistant → **Conversation agent** → the new `ha-voice` agent.
  Adding the LiteLLM integration does *not* do this automatically — it
  only creates the `conversation.*` entity.

Confirmed directly against this household's real router (decision #41/#42):
persona-correct responses and genuine, verified device control (real state
changes, accurate `success`/`failed` metadata — notably *more* reliable
here than the HACS-based Custom Conversation was, whose response metadata
stayed empty even on real successes).

### The one real gotcha: entity exposure, not the integration

A light that silently refused to respond to any phrasing — by every
integration tried, including HA's own **built-in, non-AI** agent — turned
out to have `"conversation": {"should_expose": false}` in its entity
registry entry (a `switch_as_x`-wrapped switch, never exposed to Assist at
all). No LLM, alias, or prompt fix could have found it; it was never in
the exposed-entity list to begin with. **If a request "doesn't recognize"
an entity that definitely exists, check its exposure state before
suspecting the model** — Settings → Voice assistants → Expose, or `{
"type": "homeassistant/expose_entity", "assistants": ["conversation"],
"entity_ids": [...], "should_expose": true }` over the websocket API.

**A second, smaller gotcha once exposure is fixed:** entity aliases work
(HA joins them into the entity's `"names"` field the model sees), but
**giving one entity multiple aliases at once measurably confused the small
`ha-voice` model** — it received `"names": "Buffet Light, Sideboard
Light"` and echoed the whole comma-joined string back as if it were one
literal (unmatchable) name, rather than trying either alternative. A
*single*, distinctive alias per ambiguous entity resolved cleanly and
reliably. Useful for the common case — two similarly-named lights in the
same area — where the model's own tool-selection otherwise favors the
*area* match over a specific entity.

### History: the HACS `custom_conversation` path (superseded here)

Before HA Core shipped `litellm` natively, this doc recommended **Custom
Conversation** via HACS (<https://github.com/michelle-avery/custom-conversation>).
It's still a reasonable choice on HA versions before 2026.8, or if you want
its specific features (Langfuse tracing, per-agent ignored-intents UI). Real
compatibility bugs were found and fixed against it this way (decisions #40,
#41) — missing `voluptuous-openapi` dependency, references to HA Core's
since-removed `llm.AssistAPI` class, and a thinking-model chat-log crash —
all fixed in the integration's own 1.7.0 release. If using it: configure it
as the **OpenAI** provider with the router's base URL (same settings as
above, but with a `/v1` suffix), persona goes in its "Customize Prompts" →
`instructions_prompt` field (mislabeled enough in the UI that it's easy to
miss — it is *not* called "Instructions Prompt" despite that being the
field's internal purpose), and API choice **Assist**.

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

- Conversation agent: HA's native LiteLLM agent (→ `ha-voice`)
- STT: HA's native Whisper add-on, TTS: HA's native Piper add-on
- Wake word: `hey_novak` (satellites) or a stock word (Voice PE)
- Expose only the entities you actually want voice-controllable.

## Latency expectations

Whisper `faster-whisper` at `auto` STT ≈ well under a second for short
commands; the 4B model's first token is fast if the engine host has it
warm. If responses feel slow, check (in order): model role is really the
4B/`ha-voice` role, thinking mode is off (non-thinking model variant),
toolset size, whisper model size.
