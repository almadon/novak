# Novak

A private AI assistant that runs on your own hardware.

You talk to it in a browser or out loud through Home Assistant. It remembers
things about you, can look things up in your notes, and can act on your behalf
through tools you choose to give it. Nothing you say to it leaves your machines.

> **Status: in real use, still being hardened.** Novak started as a single
> Mac mini deployment; as of decision #28 it's multi-platform by design —
> core services run on macOS or Linux (Unraid is the tested reference), and
> the inference engine is chosen per host rather than assumed: oMLX on
> Apple Silicon, Ollama on Linux with a GPU. The primary household
> deployment (decision #33) now runs the whole stack on a Linux/Unraid box
> day to day. What hasn't been verified yet: a real, deliberate power-cut
> test, and several documented steps still marked VERIFY. See
> [What state is this in?](#what-state-is-this-in) for the honest inventory,
> and [docs/engines.md](docs/engines.md) for the inference-engine side of
> the multi-platform design.

**LLM use:** this project is built and maintained with substantial AI
assistance (Claude Code). Architecture and review are human decisions, and
the reasoning behind each one is recorded in
[docs/decisions.md](docs/decisions.md). Individual commits disclose model
authorship in their trailers.

## What it can do

- **Chat**, in a browser, with per-person accounts.
- **Talk**, through Home Assistant voice hardware — ask questions, control the
  house, get short spoken answers.
- **Remember** things about each person, separately. You can read and edit
  those memories, and delete ones you don't want.
- **Look things up** in your own wiki, task list, and anything else you connect.
- **Run locally, on whatever you have.** Apple Silicon (oMLX) or a Linux box
  with a GPU (Ollama) — see [docs/engines.md](docs/engines.md) and the
  hardware table below. There's no cloud provider in the loop, so your
  conversations can't end up in someone's training data.

## What it isn't

Worth knowing before you invest time:

- **Not an app you install.** It's a stack of services and a setup checklist.
- **Not turnkey.** Expect an evening or two, and some troubleshooting.
- **Not as capable as ChatGPT.** A model that fits on hardware you own is
  smaller than one running in a datacentre. It's good at conversation,
  recall, and simple tools; it's weaker at hard reasoning and writing long
  correct code.
- **Not a product.** No support, no upgrade path but your own.

## What you need

| | |
|---|---|
| **A host that can run Docker** | Apple Silicon Mac, or a Linux box (Unraid is the tested reference — see [docs/cli.md](docs/cli.md)'s Unraid section). Same machine runs the model and the rest of the stack. |
| **Enough memory or VRAM for the model** | See the hardware table below for what's actually been measured. Less means smaller models, not a hard wall. |
| **A domain name** | Only if you want to reach it from outside your home. |
| **Home Assistant** | Only for voice. Everything else works without it. |
| **Patience** | See above. |

### Hardware support — tested vs. not

| Platform | Engine | Status |
|---|---|---|
| macOS, Apple Silicon | oMLX | **Tested.** The original deployment, run for months on a Mac mini M4/24GB. See [docs/omlx-settings.md](docs/omlx-settings.md). |
| Linux, Unraid 7.x, AMD GPU (RDNA3/4, Vulkan) | Ollama | **Tested.** The primary household deployment (decision #33) — real measured throughput in [docs/ollama-settings.md](docs/ollama-settings.md). |
| Linux, Unraid, NVIDIA GPU | Ollama | Untested here. Ollama supports CUDA; nothing in this stack assumes AMD specifically, but nobody has run it on this project. |
| Linux, Unraid, CPU only (no GPU) | Ollama | Untested here. Expected to work, expected to be slow — small models only. |
| Linux, not Unraid (bare Docker host) | Ollama | `docker-compose.yml` itself is plain Linux/Docker, no Unraid assumption. Only the `novak` CLI's host wiring (`scripts/bootstrap-unraid.sh`, `/boot/config/go` persistence, Compose Manager awareness) is Unraid-specific — on another Linux host, set `NOVAK_HOME` by hand and skip that script. Untested as a full deployment. |

If you run Novak somewhere not in this table, that's genuinely fine — the
design is meant to allow it (decision #28) — but treat it as unverified
until you've actually measured it, the same way everything above was.

## How it fits together

The important idea: **no single program is in charge.** The model server,
the chat interface, memory, and voice are separate pieces that all speak to
each other. Any one of them can be replaced without disturbing the rest.

```
    You, in a browser  ──▶  Open WebUI   ─┐
                                          │
    You, talking       ──▶  Home Assistant ┼──▶  the engine  (runs the model —
                                          │        oMLX or Ollama, your choice)
    You, managing      ──▶  Konzol        ─┘        │
                                                   ▼
                                     memory · notes · tasks · other tools
```

"the engine" is deliberately not fixed to one implementation — see
[docs/engines.md](docs/engines.md). Everything above it talks to whichever
engine `registry/engines.yaml` points at, by model name, not by knowing
which one is actually running.

That structure isn't tidiness for its own sake. While this was being built, the
memory system it originally used was shut down by its authors, and its most
obvious replacement turned out to be discontinued too. Swapping it meant
replacing one service. In an all-in-one product, that's a migration.

## Where things run, and what's reachable

One host runs the whole stack — the model, memory, voice, chat frontend, all
of it (decision #28/#33). The only thing that's ever a separate machine is
the reverse proxy that terminates TLS and, optionally, faces the public
internet — nothing in Novak's own containers is port-forwarded.

| | Runs | Reachable from |
|---|---|---|
| **The Novak host** (macOS or Linux, home) | everything: the engine, memory, voice, chat frontend, console | your network and Tailscale only — **nothing is port-forwarded** |
| **A reverse proxy** (your own — a VPS, a LAN-neighboring box, whatever you already run) | TLS termination, and optionally public exposure for the chat frontend only | the public internet, if you choose to expose anything at all |

The proxy reaches the Novak host over [Tailscale](https://tailscale.com), a
private network between your own devices — or plain LAN, if you're not
exposing anything publicly. Either way, the host itself accepts no incoming
connections it wasn't specifically configured to.

Traffic between Tailscale devices is already encrypted, so that hop is
covered. Traffic across your **local** network is not, by default — see
[docs/proxy.md](docs/proxy.md) for putting HTTPS in front of these services
using a reverse proxy you already run.

This is deliberate. The chat interface is designed to face the internet. The
model server and the memory service are not — they assume everyone talking to
them is friendly. See [docs/architecture.md](docs/architecture.md) for the
full placement reasoning and what's actually running where today.

## Setting it up

Work through **[docs/deploy-checklist.md](docs/deploy-checklist.md)** — it's
the real instructions, with a column for macOS and a column for Unraid where
a step actually differs. This is the shape of it so you know what you're in
for.

Most of it is driven by one command: `novak status` tells you what is
unconfigured and the exact command to fix each thing — same command, same
output shape, on either platform (see [docs/cli.md](docs/cli.md)).

**Before you touch the host:**

1. **Build the integration images.** The tools live in a separate repo,
   [novak-integracije](https://github.com/almadon/novak-integracije), and are used here as
   prebuilt images. They need building once.
2. **Optional: the web console.** [novak-konzol](https://github.com/almadon/novak-konzol) is a
   separate, optional piece for managing people and memories. Skip it to start —
   everything it does can be done by editing a file.

**On macOS:**

3. Copy this repo over.
4. Put your passwords and API keys in the macOS Keychain — see
   [docs/security.md](docs/security.md). The startup script refuses to run with
   placeholder values still in place.
5. Run `./scripts/bootstrap-admin.sh --service-user novak` from an admin
   account (installs OrbStack and oMLX system-wide, sets the power profile),
   then `./scripts/bootstrap.sh` as the account that will run the stack.
6. Follow the checklist for the parts that need a human: downloading models,
   connecting Home Assistant, and so on.

**On Unraid (Linux):**

3. Clone this repo somewhere on the array or cache pool (e.g.
   `/mnt/cache/appdata/Novak/repo`).
4. Run `./scripts/bootstrap-unraid.sh` as root — it links the `novak` CLI
   onto PATH, persists that across reboots (required on this platform, see
   [docs/cli.md](docs/cli.md)), and tells you the next steps.
5. `novak up` seeds `.env`; `novak secret set <VAR>` for each secret it
   lists as missing — real values directly in `.env` here, since there's no
   OS keychain to use headlessly (see [scripts/lib/secrets.sh](scripts/lib/secrets.sh)).
6. Register the deployment as a Compose Manager stack (Docker tab -> Compose
   Manager -> Add New Stack -> Indirect Config File), then follow the
   checklist for the rest.

**Memory** runs in the same stack and ships its own database, so there is
nothing separate to stand up — but two settings decide whether it is private
and whether it is safe. See [docs/memory-setup.md](docs/memory-setup.md).

## What state is this in?

Honest inventory:

| Part | State |
|---|---|
| The design and the reasoning | Settled, written down |
| macOS/oMLX deployment | Run for months, real daily use |
| Linux/Unraid/Ollama deployment | Run daily as the primary household deployment (decision #33) since late Aug 2026; survived a real reboot (decision #37) — all 8 containers came back unaided, no manual step |
| The `novak` CLI on Unraid | Built and tested end to end this cycle (decision #35) — `status`, `secret`, `drift`, `adopt`, `ports`, `router apply`, `checklist` all verified against a real host |
| The web console | Scaffolding, **never run** |
| Everything else | Other people's software, configured but untested here |

Anything marked `VERIFY` in a file is something that couldn't be checked without
the actual hardware.

## Documentation

All of it lives in [docs/](docs/README.md) — that index is the fullest map.

**Start here:**

| | |
|---|---|
| [How memory works](docs/how-memory-works.md) | What "memory" actually means, in plain language |
| [What sets Novak apart](docs/what-sets-novak-apart.md) | Why build it this way, and what it costs |
| [Deploy checklist](docs/deploy-checklist.md) | The real setup instructions |
| [Where this got to](docs/STATE.md) | **Read first if picking this up** — current state and open problems |
| [Running headless](docs/headless-operation.md) | Unattended restarts, and the FileVault trade-off |
| [Memory setup](docs/memory-setup.md) | Standing up the memory backend (not run by our compose) |

**Going deeper:**

| | |
|---|---|
| [Architecture](docs/architecture.md) | How the pieces fit, and why each is where it is |
| [Decisions](docs/decisions.md) | Every significant choice, with reasoning and cost |
| [Commit style](docs/commit-style.md) | Conventional Commits, enforced by a hook |
| [Security](docs/security.md) | Secrets, permissions, and what the risks actually are |
| [Home Assistant](docs/home-assistant.md) | Voice setup |
| [Credits](docs/credits.md) | Whose software this is built from |
| [oMLX settings](docs/omlx-settings.md) | Which models, how to tune them, and applying profiles (macOS) |
| [Ollama settings](docs/ollama-settings.md) | Same, for the Linux/GPU engine — real measured throughput |
| [Inference engines](docs/engines.md) | How the engine choice itself works, and how to add one |

**Reference:**

| | |
|---|---|
| [CLI reference](docs/cli.md) | Every `novak` command, and how secrets are classified |
| [scripts/novak](scripts/novak) | The CLI itself |
| [registry/mcp-servers.yaml](registry/mcp-servers.yaml) | Which tools are installed, and how risky each is |
| [registry/omlx.yaml](registry/omlx.yaml) | Which models exist, and the profiles they expose |
| [reconciler/](reconciler/reconcile.py) | Applies that list. The only thing here that controls containers |
| [prompts/](prompts/novak-chat.md) | The assistant's personality — the master copy each client is given |
| [wakeword/](docs/wakeword.md) | Teaching it to answer to "Hey Novak" |

## The three repositories

| | |
|---|---|
| **novak** (this one) | The stack: what runs, how it's configured, and why |
| [novak-integracije](https://github.com/almadon/novak-integracije) | Tools and integrations — the part that grows |
| [novak-konzol](https://github.com/almadon/novak-konzol) | Optional web interface for managing it |

## A note on adding things

New capabilities are added as **tools the assistant can call**, not as features
bolted into a user interface. That way every client — chat, voice, anything
added later — gets them at once.

Powerful tools are allowed, but the ones that can change your system or act
irreversibly have to be switched on deliberately: the file records what a tool
can do, who agreed to it, and when. Turning it back off takes nothing. The
point isn't to stop you; it's so that in a year you can see what you agreed to.
