# Novak

A private AI assistant that runs on your own hardware.

You talk to it in a browser or out loud through Home Assistant. It remembers
things about you, can look things up in your notes, and can act on your behalf
through tools you choose to give it. Nothing you say to it leaves your machines.

> **Status: in testing.** The stack is deployed and running on one Mac mini,
> and it comes back on its own after a reboot. It has not run unattended for
> long, has never survived a real power cut, and several documented steps are
> still marked VERIFY. See [What state is this in?](#what-state-is-this-in)
> for what is actually confirmed.

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
- **Run locally.** The model runs on your Mac. There's no cloud provider in the
  loop, so your conversations can't end up in someone's training data.

## What it isn't

Worth knowing before you invest time:

- **Not an app you install.** It's a stack of services and a setup checklist.
- **Not turnkey.** Expect an evening or two, and some troubleshooting.
- **Not as capable as ChatGPT.** A model that fits on a Mac mini is smaller than
  one running in a datacentre. It's good at conversation, recall, and simple
  tools; it's weaker at hard reasoning and writing long correct code.
- **Not a product.** No support, no upgrade path but your own.

## What you need

| | |
|---|---|
| **A Mac** | Apple Silicon. This is tuned for a Mac mini M4 with 24GB. Less memory means smaller models. |
| **Somewhere to run containers** | The same Mac is fine. |
| **A domain name** | Only if you want to reach it from outside your home. |
| **Home Assistant** | Only for voice. Everything else works without it. |
| **Patience** | See above. |

## How it fits together

The important idea: **no single program is in charge.** The model server,
the chat interface, memory, and voice are separate pieces that all speak to
each other. Any one of them can be replaced without disturbing the rest.

```
    You, in a browser  ──▶  Open WebUI   ─┐
                                          │
    You, talking       ──▶  Home Assistant ┼──▶  oMLX  (runs the model)
                                          │        │
    You, managing      ──▶  Konzol        ─┘        │
                                                   ▼
                                     memory · notes · tasks · other tools
```

That structure isn't tidiness for its own sake. While this was being built, the
memory system it originally used was shut down by its authors, and its most
obvious replacement turned out to be discontinued too. Swapping it meant
replacing one service. In an all-in-one product, that's a migration.

## Where things run, and what's reachable

Two machines, and only one of them is on the internet.

| | Runs | Reachable from |
|---|---|---|
| **The Mac** (home) | the model, memory, voice | your network and Tailscale only — **nothing is port-forwarded** |
| **A small VPS** | Open WebUI, and the reverse proxy that terminates TLS | the public internet |

The VPS reaches the Mac over [Tailscale](https://tailscale.com), a private
network between your own devices. So you can use the chat interface from
anywhere, while your home network accepts no incoming connections at all.

Traffic between Tailscale devices is already encrypted, so that hop is covered.
Traffic across your **local** network is not, by default — see
[proxy/](docs/proxy.md) for putting HTTPS in front of these services using a
reverse proxy you already run.

This is deliberate. The chat interface is designed to face the internet. The
model server and the memory service are not — they assume everyone talking to
them is friendly.

## Setting it up

Work through **[docs/deploy-checklist.md](docs/deploy-checklist.md)** — it's the
real instructions, in eleven phases, in the order you actually do them. This is
the shape of it so you know what you're in for.

Most of it is driven by one command: `novak status` tells you what is
unconfigured and the exact command to fix each thing.

**Before you touch the Mac:**

1. **Build the integration images.** The tools live in a separate repo,
   [novak-integracije](https://github.com/almadon/novak-integracije), and are used here as
   prebuilt images. They need building once.
2. **Optional: the web console.** [novak-konzol](https://github.com/almadon/novak-konzol) is a
   separate, optional piece for managing people and memories. Skip it to start —
   everything it does can be done by editing a file.

**On the Mac:**

2. Copy this repo over.
3. Put your passwords and API keys in the macOS Keychain — see
   [docs/security.md](docs/security.md). The startup script refuses to run with
   placeholder values still in place.
4. Run `./scripts/bootstrap-admin.sh --service-user novak` from an admin
   account (installs OrbStack and oMLX system-wide, sets the power profile),
   then `./scripts/bootstrap.sh` as the account that will run the stack.
5. Follow the checklist for the parts that need a human: downloading models,
   connecting Home Assistant, and so on.

**Memory** runs in the same stack and ships its own database, so there is
nothing separate to stand up — but two settings decide whether it is private
and whether it is safe. See [docs/memory-setup.md](docs/memory-setup.md).

## What state is this in?

Honest inventory:

| Part | State |
|---|---|
| The design and the reasoning | Settled, written down |
| Configuration and docs | Written, unverified against a real machine |
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
| [oMLX settings](docs/omlx-settings.md) | Which models, how to tune them, and applying profiles |

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
