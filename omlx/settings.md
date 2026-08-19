# oMLX configuration for the 24GB mini

Apply these in the oMLX admin panel (`http://localhost:<port>/admin`) or
`~/.omlx/settings.json`. Exact setting names may differ slightly between
oMLX versions — the *values and rationale* below are the deliverable; map
them onto whatever the admin UI calls them.

## Server-wide

| Setting | Value | Why |
|---|---|---|
| Max process memory | default (RAM − 8GB ≈ 16GB) | The "nice"-like balloon: oMLX can use up to ~16GB, macOS always keeps ~8GB, LRU-evicts models under pressure. Leave the default. |
| API key auth | **enable** | Anything on the LAN can otherwise use the server. Store the key in Keychain as `novak/OMLX_API_KEY`. |
| Bind address | LAN interface | Needed so Docker containers and HA can reach it. Do not port-forward from the router. |
| SSD KV cache (DFlash) | enable, generous size (50GB+) | Warm restarts + fast repeated-prefix prefill (HA system prompts, Open WebUI personas). SSD is cheap; latency isn't. |

## Models (download via admin UI → HuggingFace search)

| Role | Model | ~RAM | Idle TTL |
|---|---|---|---|
| Voice / quick tools | `mlx-community/Qwen3-4B-Instruct-2507-4bit` | ~2.5GB | **none — always loaded.** Voice latency cannot absorb a model load. |
| Main chat | `mlx-community/Qwen3-14B-4bit` | ~8.5GB | 15–30 min. Unloads when you're at the desk doing other things; SSD cache makes reloads warm. |
| Embeddings (memory/RAG) | small MLX embedding model if oMLX serves `/v1/embeddings` — **verify**; otherwise let Mem0/Open WebUI use their built-in local embedders | <1GB | none |

Worst case all-hot ≈ 12GB — inside the 16GB ceiling with the OS comfortable.
Do **not** add a 30B-class model on this machine; 4-bit ≈ 17GB will fight
your desktop session.

## Profiles

Profiles expose one loaded model as several virtual models with different
settings — no extra RAM. Create:

- **`ha-voice`** → Qwen3-4B: temperature ~0.3, short max tokens (voice
  answers should be one or two sentences), reasoning/thinking OFF if the
  model supports toggling it (latency).
  System prompt: [../prompts/novak-voice.md](../prompts/novak-voice.md)
- **`chat`** → Qwen3-14B: your defaults for conversation.
  System prompt: [../prompts/novak-chat.md](../prompts/novak-chat.md)
- **`deep`** → Qwen3-14B: thinking ON, higher max tokens, for harder
  questions. Same chat persona.

Clients select these by their **exposed** id, which is the base model and the
profile joined by a colon — not the bare profile name:

```
Qwen3-4B-Instruct-2507-4bit:ha-voice
Qwen3-14B-4bit:chat
Qwen3-14B-4bit:deep
```

Confirmed against a running server. A profile also has to be marked
`expose_as_model`, or it exists and no client can select it —
[`novak omlx apply`](../docs/cli.md) sets that for every profile it writes.

Apply these from [`registry/omlx.yaml`](../registry/omlx.yaml) rather than by
hand: `novak omlx apply`.

**Novak does not choose models for you.** There is no automatic routing by task
difficulty — the client picks a profile and that's what answers. HA is pinned to
`ha-voice` because voice can't wait for a model load; in Open WebUI you pick from
the dropdown. Automatic tier-switching (easy questions → 4B, hard → 14B) would be
a real feature to build, not something that exists today.

**On where the persona lives**: **profiles cannot hold it.** Checked against
oMLX itself — a profile's fields are sampling, thinking and cache tuning
(`temperature`, `top_p`, `enable_thinking`, the DFlash/TurboQuant knobs) and
there is no system-prompt field.

So the persona is set per client: Open WebUI's model preset, Home Assistant's
agent prompt field. [`../prompts/`](../prompts/) is the master copy and the
copies **will** drift — that is a maintenance cost, not an oversight. See
decision 17 in [../docs/decisions.md](../docs/decisions.md).

## If desktop contention is ever still noticeable

The defaults + idle TTLs should already behave well. If not, add a launchd
job that polls console idle time (`ioreg -c IOHIDSystem | awk
'/HIDIdleTime/'`) and unloads the 14B via the admin API when you're active.
Don't build this preemptively.
