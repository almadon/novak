# Inference engines: choosing hardware and backend

Novak's core (Hindsight, Open WebUI, the console, voice, the MCP registry)
runs on any real Docker host. The one piece that doesn't generalize for free
is inference — different hardware wants a different engine, and this doc is
where that choice is supposed to live. See decision #28 in
[decisions.md](decisions.md) for why this exists and what it replaced.

## The contract

An engine is anything that serves an OpenAI-compatible
`/v1/chat/completions` endpoint. That's the whole requirement. Novak's
router (`router/config.yaml`, decision #21/#23) only ever talks to an
`api_base` — it has no idea what's behind it, and it needs no idea. This is
deliberate, not incidental: it's what makes the rest of this doc possible
without touching the router at all.

Two engines are documented today. Both are real, both are running, neither
is a fallback for the other — they're siblings, chosen per model based on
what each host's hardware actually does well.

## oMLX — Apple Silicon, native

Runs directly on macOS (Metal/MLX can't run in a Linux container, which is
why this one isn't Dockerized like everything else). Settings, model
choices, and the RAM-budget reasoning for a specific machine:
[omlx-settings.md](omlx-settings.md).

Good fit for: any model that fits comfortably in the host's unified memory,
where a Mac is already part of the household's hardware anyway.

## Ollama — Linux, Vulkan or ROCm

Runs as an ordinary container — confirmed directly, `--device=/dev/dri`
passthrough with no vendor plugin required for AMD hardware. On RDNA4
specifically (checked directly against a real RX 9060 XT): Vulkan
(`OLLAMA_VULKAN=1`) beats ROCm and needs no `HSA_OVERRIDE_GFX_VERSION`
workarounds. `OLLAMA_MAX_LOADED_MODELS` / `OLLAMA_NUM_PARALLEL` give the
same multi-model, multi-user behavior oMLX's own TTL/profile system does,
natively. Full reasoning, real numbers, and the compose file:
[ollama-settings.md](ollama-settings.md).

Good fit for: a Linux box with a discrete GPU, especially one already
running other services — no VM, no exclusive GPU ownership required, so the
card stays usable by anything else on the same host.

VERIFY before treating as settled: real generation numbers exist for two
model sizes on one specific card (RX 9060 XT, 16GB) — `qwen3:4b` at 94.8
tok/s, `qwen3:14b` at 32.6 tok/s, both fully VRAM-resident. Numbers on
different hardware will differ; re-measure rather than assume.

## Same model role, different engine — this is the point

The router doesn't care which engine answers `chat`, `deep`, or `ha-voice`
— it's just a `model_name` → `api_base` mapping. Nothing stops different
roles pointing at different engines simultaneously, which is exactly what
this household runs: `chat` and `deep`'s smaller tiers on Ollama/Spire
(fast, fits VRAM cleanly), while a model too large for that card
(Qwen3.8-27B, confirmed not fitting RX 9060 XT's 16GB — see decision #28)
stays on oMLX/Mitochon instead, because that's the hardware it actually
fits.

This is a real, working `router/config.yaml` shape, not a hypothetical:

```yaml
model_list:
  - model_name: chat
    litellm_params:
      model: openai/qwen3:14b
      api_base: http://spire.tailnet-name.ts.net:11434/v1
      api_key: none
  - model_name: deep
    litellm_params:
      model: openai/hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M
      api_base: http://mitochon.tailnet-name.ts.net:8000/v1
      api_key: os.environ/OMLX_API_KEY
```

(Illustrative — the actual `DEFAULT_ENGINE_BASE_URL`/`OMLX_API_KEY` wiring in this
repo's `docker-compose.yml` and `.env.example` hasn't been generalized to a
multi-host, multi-engine registry yet. See "Not built yet" below.)

## Choosing at setup time

**Not built yet.** `bootstrap.sh` and the `novak` CLI still assume macOS +
OrbStack + oMLX end to end — this section describes the intended shape, not
a shipped mechanism. Filed as an open item from decision #28, not
implemented here.

The intended shape: a declarative engine registry, the same pattern
`registry/mcp-servers.yaml` already uses for MCP servers — one entry per
engine, its host, its reachable models, applied and drift-checked the same
way. `bootstrap.sh` would ask which engine(s) this deployment uses (or read
it from that registry) instead of assuming oMLX is always present. Until
that lands, wiring a second engine in means hand-editing
`router/config.yaml` directly, as done here.

## Adding a third engine

Nothing here is oMLX/Ollama-specific in principle. Any engine that speaks
OpenAI-compatible `/v1/chat/completions` qualifies — vLLM, a raw
`llama-server`, a hosted-but-self-controlled endpoint, whatever fits the
hardware in question. Give it its own settings doc (sibling to
`omlx-settings.md` and this one), point a `router/config.yaml` entry at it,
and it's a real Novak engine — no code in the router itself changes.
