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
| Deep / hard questions | `hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ4_XS` | Fully resident, ~14GB | **19.43 tok/s** |

**`UD-Q4_K_M` (17GB) does not fit this GPU** — confirmed directly, not
assumed: `ollama ps` showed a genuine 12%/88% CPU/GPU layer split even
with the entire card free, and eval rate was ~10 tok/s, roughly a third
of what simple size-scaling from the 14B would predict (the CPU-offloaded
layers dragging the whole batch down).

**`UD-IQ4_XS` (14GB) fits, and is now the `deep`-role model on Spire**
(decision #33) — replacing oMLX/Mitochon for this role. `ollama ps`
confirms `100% GPU`, no CPU offload at all. Eval rate roughly doubled
versus the ill-fitting `Q4_K_M` (19.43 vs. ~10 tok/s), and — the more
consequential number for a memory-constrained card — it no longer
competes with other loaded models for the CPU-offload penalty at all,
since none of its layers ever land on CPU. File size was HEAD-verified
against HuggingFace's `resolve/main/` content-length (following the Xet
CDN redirect — the bare URL's own Content-Length is a small JSON
redirect body, not the file) before pulling: 14,252,845,984 bytes
(~13.3 GiB), not assumed from the `api/models` listing, which doesn't
reliably expose per-file sizes for this repo.

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

Model weights live on `/mnt/teracache/Novak/models/ollama` — moved there
from the original `/mnt/teracache/appdata/Ollama/data` as part of decision
#33's storage reorg, same pool (a fast rename, not a copy), just under the
shared `Novak/` structure instead of a standalone appdata directory.

## Applying this today: `docker-compose.yml`, gated behind a profile

**As of decision #33, Ollama is folded into the shared `docker-compose.yml`**
as a service gated behind `profiles: ["ollama"]` — no more standalone
Compose Manager project. Enable it by adding `"ollama"` to the stack's
active profiles (Compose Manager's `profiles` file, or `COMPOSE_PROFILES`)
and setting `OLLAMA_DATA_DIR` in `.env` to wherever the model weights
should live. Models themselves are still pulled by hand —
`docker exec <ollama-container> ollama pull <tag>` — since the
declarative, `registry/omlx.yaml`-style setup script for Ollama models
that `engines.md` names as still-missing work doesn't exist yet. Until it
does, model changes need to be made and recorded by hand — including
updating this doc when they are.

The relevant `.env` block, for reference (see `.env.example` for the full,
commented version):

```
OLLAMA_PORT=11434
OLLAMA_VULKAN=1
OLLAMA_MAX_LOADED_MODELS=2
OLLAMA_NUM_PARALLEL=4
OLLAMA_KEEP_ALIVE=20m
OLLAMA_DATA_DIR=/mnt/teracache/Novak/models/ollama
```

## What was actually measured

All three numbers are real generations (`ollama run <model> "..." --verbose`),
not synthetic benchmarks, run directly against this hardware
(AMD Radeon RX 9060 XT, 16GB, RDNA4/`gfx1201`, Vulkan backend):

```
qwen3:4b                                  eval rate: 94.80 tokens/s
qwen3:14b                                 eval rate: 32.60 tokens/s
hf.co/unsloth/Qwen3.8-27B-GGUF:UD-Q4_K_M  eval rate: 10.15 tokens/s (12%/88% CPU/GPU split)
hf.co/unsloth/Qwen3.8-27B-GGUF:UD-IQ4_XS  eval rate: 19.43 tokens/s (100% GPU, decision #33)
```

Re-measure rather than trust these on different hardware, a different
quant, or after an Ollama/driver update — none of this is guaranteed
stable across versions.
