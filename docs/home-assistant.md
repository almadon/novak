# Home Assistant + HA Voice wiring

HA stays wherever it runs today; the mini serves it three endpoints:
LLM (oMLX), STT (Wyoming whisper), TTS (Wyoming piper), plus MCP tools.

## 1. Conversation agent → oMLX

HA's stock OpenAI integration doesn't accept a custom base URL. Install
**openai-compatible-conversation** via HACS
(<https://github.com/michelle-avery/openai-compatible-conversation>) — a
clean fork of the built-in agent with a base-URL field. If you want the
agent to *control devices* through function calling instead of HA's
built-in intent handling, use **Extended OpenAI Conversation**
(<https://github.com/jekalmin/extended_openai_conversation>) instead.

Settings:

- Base URL: `http://<mini>:<OMLX_PORT>/v1`
- API key: the oMLX key
- Model: `ha-voice` (the fast 4B profile — voice latency is unforgiving)
- System prompt: [../prompts/novak-voice.md](../prompts/novak-voice.md)
  (skip if the oMLX profile already carries it — don't set it twice).
  Keep it short: long prompts produce long spoken answers.

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
