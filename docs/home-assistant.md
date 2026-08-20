# Home Assistant + HA Voice wiring

HA stays wherever it runs today; the mini serves it three endpoints:
LLM (oMLX), STT (Wyoming whisper), TTS (Wyoming piper), plus MCP tools.

## 1. Conversation agent → oMLX

HA's stock OpenAI integration still doesn't accept a custom base URL
([core#137087](https://github.com/home-assistant/core/issues/137087)), so this
needs a custom component. Install **Custom Conversation** via HACS
(<https://github.com/michelle-avery/custom-conversation>).

It lets you keep HA's built-in Assist API for device control, which is what
this stack wants: the conversation agent handles *language*, and tools arrive
through HA's MCP integration (§3). It can also run both — built-in intents
first, the LLM for whatever they don't match.

Configure it as the **OpenAI** provider and override the base URL — its
[supported providers](https://github.com/michelle-avery/custom-conversation/blob/main/docs/supported-providers.md)
doc confirms that is how arbitrary self-hosted endpoints are meant to be used,
while warning that *"supposedly 'OpenAI-compatible' APIs are sometimes not
fully compatible."* It reaches the endpoint through LiteLLM, so there is a
translation layer between HA and oMLX that neither project tests against the
other. **VERIFY** a real voice turn end to end before trusting it; oMLX serves
both `/v1/chat/completions` and `/v1/responses`, so the raw surface is there,
but that is not the same as the pairing having been exercised.

> **If you are following an older copy of these notes**, they recommended
> `openai-compatible-conversation`. Its maintainer has since disclaimed it —
> *"I personally cannot support this, as I don't actually use this
> integration"* — and points at Custom Conversation, which is the same author
> and actively maintained. See decision 19 for the full comparison, including
> when Extended OpenAI Conversation is the better answer.

Settings:

- Base URL: `http://<mini>:<OMLX_PORT>/v1`
- API key: the oMLX key
- Model: **`Qwen3-4B-Instruct-2507-4bit:ha-voice`** — the exposed id is the
  base model and the profile joined by a colon, not the bare profile name.
  `novak omlx apply` prints the exact strings; so does `GET /v1/models`.
- System prompt: [../prompts/novak-voice.md](../prompts/novak-voice.md).
  **Set it here** — oMLX profiles have no system-prompt field (decision 17),
  so there is no risk of setting it twice and no single place that every
  client inherits from. Keep it short: long prompts produce long spoken
  answers.

## 2. Wyoming STT/TTS

Settings → Devices & Services → Add Integration → **Wyoming Protocol**,
twice:

- STT: `tcp://<mini>:10300` (whisper)
- TTS: `tcp://<mini>:10200` (piper)

Note: upstream Piper was archived in Oct 2025. The container still works;
if voice quality bothers you later, swap the `piper` compose service for a
Kokoro-based Wyoming wrapper — one service block, nothing else changes.

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

## 4. Wake word — "Hey Novak"

Add a third Wyoming integration pointing at `tcp://<mini>:10400` for the
openWakeWord service, then select the wake word in the pipeline below.

Read [wakeword.md](wakeword.md) first — it covers
training the model (synthetic, ~no effort) and one significant constraint:
**HA Voice PE hardware detects wake words on-device with microWakeWord,
which has no custom-training path**, so "Hey Novak" works for Wyoming
satellites but not (currently) for Voice PE. On Voice PE, keep a stock
trigger like "okay nabu" — the assistant still answers as Novak.

## 5. Assist pipeline

Settings → Voice assistants → Add assistant, named **Novak**:

- Conversation agent: the openai-compatible agent (→ `ha-voice`)
- STT: whisper, TTS: piper
- Wake word: `hey_novak` (satellites) or a stock word (Voice PE)
- Expose only the entities you actually want voice-controllable.

## Latency expectations

Whisper `small-int8` STT ≈ well under a second for short commands; 4B
model first token is fast, and repeated system-prompt prefill hits the SSD
cache. If responses feel slow, check (in order): model profile is really
the 4B, thinking mode is off, toolset size, whisper model size.
