# Ollama configuration for RDNA4 (Spire, RX 9060 XT)

Sibling to [omlx-settings.md](omlx-settings.md) — same purpose, different
engine. See [engines.md](engines.md) for why both exist side by side, and
decision #28 in [decisions.md](decisions.md) for the full story of how this
one was verified.

Everything below was measured directly against the real hardware, not
estimated from someone else's benchmark — see "What was actually measured"
at the end for the raw numbers this reasoning rests on.

## Server-wide

| Setting | Value | Why |
|---|---|---|
| Backend | `OLLAMA_VULKAN=1` | Confirmed directly: Vulkan beats ROCm on RDNA4 specifically (two independent published benchmarks agreed, and this matched on real hardware here) — the opposite of the usual "ROCm is faster" assumption from older AMD generations. Needs zero `HSA_OVERRIDE_GFX_VERSION` hacks; ROCm on `gfx1201` still does on some setups. |
| GPU device passthrough | `--device /dev/dri:/dev/dri --device /dev/kfd:/dev/kfd` | Plain Docker device mapping — confirmed no vendor plugin needed for AMD (unlike NVIDIA's container toolkit requirement). `/dev/kfd` isn't strictly required for the Vulkan path but costs nothing to include, and keeps the ROCm path available if you ever want to compare. |
| `OLLAMA_MAX_LOADED_MODELS` | `2` | Not a hard cap on capability — Ollama evicts to make room regardless of this number when something bigger is requested. It just stops Ollama from ever trying to keep a 3rd "resident" slot memory was never going to allow, given what's actually loaded here (see Models below). |
| `OLLAMA_NUM_PARALLEL` | `4` | The actual multi-model/multi-user requirement — concurrent requests per loaded model, not just multiple models existing. |
| `OLLAMA_KEEP_ALIVE` | `20m` | Same idle-unload shape as oMLX's per-model TTL, just a single server-wide value rather than per-model (Ollama doesn't expose per-model TTL the way oMLX's registry does). |

## Models

| Role | Model | VRAM fit (16GB card) | Eval rate (measured) |
|---|---|---|---|
| Voice / quick tools | `qwen3:4b` (`qwen3:4b-instruct-2507-q4` is the closer match to oMLX's own voice model if you want the exact same weights) | Fully resident, ~2.5GB | **94.8 tok/s** |
| Main chat | `qwen3:14b` | Fully resident, ~9.3GB | **32.6 tok/s** |
| Deep / hard questions | *Not this card* — see below | — | — |

**Qwen3.8-27B does not fit this GPU.** Confirmed directly, not assumed:
`hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M` is ~17GB against a 15.9GB VRAM
ceiling. `ollama ps` shows a genuine 12%/88% CPU/GPU layer split **even
with the entire card free** — this isn't a contention artifact from other
loaded models, it's a real fit problem. Eval rate there was ~10 tok/s,
roughly a third of what simple size-scaling from the 14B would predict,
which is the CPU-offloaded layers dragging the whole batch down. Per
decision #28, this model stays on oMLX/Mitochon instead — matching the
model to hardware that actually fits it, not forcing one card to do
everything.

**A smaller quant might fit and hasn't been tested**: `Qwen3.8-27B-UD-Q4_K_S.gguf`
or `-IQ4_XS` are both smaller than the `Q4_K_M` measured above. Worth
trying if you want a `deep`-class model on this card specifically, before
concluding the answer is permanently "use the other engine."

### The model's own naming quirk to know about

Unsloth's GGUF repos name quants like `Qwen3.8-27B-UD-Q4_K_M.gguf` — the
`UD-` prefix (Unsloth Dynamic) is part of the actual filename. Ollama's
`hf.co/` tag resolution needs the **exact** suffix to match:
`hf.co/unsloth/Qwen3.8-27B-GGUF:Q4_K_M` silently resolves to the wrong
blobs (confirmed directly — it downloaded ~17GB of *something*, wrote no
manifest, and `ollama list` never showed it). The working tag is
`hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M` — check a repo's actual
filenames before assuming the plain quant name works as a tag.

## MTP speculative decoding — real, but not through Ollama today

This exact GGUF ships with MTP (multi-token prediction) draft layers
built in, which `llama.cpp` can use for real self-speculative decoding —
independently documented as roughly 2x on dense models when it works.
**Confirmed directly that this isn't reachable through Ollama yet**:
Ollama's own MTP support exists only on its MLX runner (Apple Silicon)
today, not the Vulkan/AMD backend used here. Getting it would mean
running raw `llama-server` with `--spec-type draft-mtp` instead of
Ollama — a second inference engine's worth of lifecycle and multi-model
complexity, for one model. Not done; see decision #28's "what would
justify revisiting."

## Storage

Model weights live on `/mnt/teracache/appdata/Ollama/data` (an Unraid
pool with ample free space at the time this was set up), not the smaller
`/mnt/cache` NVMe pool most of Spire's other appdata uses — deliberately
asked about before choosing, since a 27B-class model's ~17GB alone would
have eaten most of `/mnt/cache`'s free space. Check actual free space on
whichever pool you point at before committing; this isn't a fixed rule,
just what fit at the time.

## Applying this today: by hand, not a `novak` command

**Unlike oMLX, there is no `novak ollama apply` (or equivalent) yet.**
Everything above was applied directly — a `docker-compose.yml` written
by hand and registered with Unraid's Compose Manager plugin, models
pulled with `docker exec ollama ollama pull <tag>`. This is the real gap
`engines.md` names as the setup-script work still ahead: a declarative,
`registry/omlx.yaml`-style file for Ollama models, applied and
drift-checked the same way, doesn't exist. Until it does, changes here
need to be made and recorded by hand — including updating this doc when
they are.

The compose file, for reference (adjust the volume path to wherever you
actually have room):

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    network_mode: bridge
    ports:
      - 11434:11434
    devices:
      - /dev/dri:/dev/dri
      - /dev/kfd:/dev/kfd
    volumes:
      - /mnt/teracache/appdata/Ollama/data:/root/.ollama
    environment:
      - OLLAMA_VULKAN=1
      - OLLAMA_MAX_LOADED_MODELS=2
      - OLLAMA_NUM_PARALLEL=4
      - OLLAMA_KEEP_ALIVE=20m
```

## What was actually measured

All three numbers are real generations (`ollama run <model> "..." --verbose`),
not synthetic benchmarks, run directly against this hardware
(AMD Radeon RX 9060 XT, 16GB, RDNA4/`gfx1201`, Vulkan backend):

```
qwen3:4b                                 eval rate: 94.80 tokens/s
qwen3:14b                                eval rate: 32.60 tokens/s
hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M  eval rate: 10.15 tokens/s (12%/88% CPU/GPU split)
```

Re-measure rather than trust these on different hardware, a different
quant, or after an Ollama/driver update — none of this is guaranteed
stable across versions.
