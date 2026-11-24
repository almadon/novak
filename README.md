# Novak

**A private AI assistant that runs on your own hardware, with a memory and a set of tools for each person in the house.**

You talk to Novak in a browser or out loud through Home Assistant. It remembers things about you, looks things up in your notes, and acts on your behalf through tools you choose to give it. The model runs on a machine you own, so conversations never reach a cloud provider.

> **Status: in testing.** It is in daily use on one household's server, but it is still being hardened, and several documented steps are marked `VERIFY` because they have not been checked on real hardware. The honest inventory is in [What state is this in?](#what-state-is-this-in).
> This project comes with no warranty or guarantee of fitness for any purpose. Use it at your own risk.
>
> **LLM use.** Built and maintained with substantial AI assistance (Claude Code). Architecture and review are human decisions, and the reasoning behind each one is recorded in [docs/decisions.md](docs/decisions.md). Commits name the model in their trailers. See [AGENTS.md](AGENTS.md).

<p align="center">
  <img src="docs/images/architecture.svg" alt="Clients on top talk to a services layer: a router in front of the inference engine, and a gateway that knows who is asking. The gateway reaches memory, notes, tasks, the house and search over MCP. The console reads status from the gateway and sends it change requests." width="100%">
</p>

## What it does

Novak is a stack of separate services, not one program. A model server (Ollama on Linux, oMLX on Apple Silicon) answers questions. A router in front of it gives every client the same persona and the same model names. Memory, notes, tasks and the house are standalone services that speak MCP, and a gateway sits in front of them so each person reaches only their own tools with their own credentials. Removals are held until that person confirms on their phone, and every call is logged by the name of its arguments, never their values.

Any one piece can be replaced without disturbing the rest. That matters in practice: the memory system this project started with was shut down by its authors while it was being built, and swapping it meant replacing one service, not migrating a product.

## Use cases

- **A household assistant that keeps people apart.** Two people each get their own memory, their own tasks and their own Home Assistant voice agent, and neither can read the other's.
- **Voice control of the house without a cloud.** "Turn off the lights, then remind me about the plumber" runs on a machine you own.
- **An assistant for people who already self-host.** If you run a wiki, a task list and Home Assistant, Novak connects them behind one door instead of asking you to move into someone's app.

## What it isn't

- **Not an app you install.** It is a stack of services and a setup checklist.
- **Not turnkey.** Expect an evening or two, and some troubleshooting.
- **Not as capable as the large hosted models.** A model that fits on hardware you own is smaller. It is good at conversation, recall and simple tools, and weaker at hard reasoning and long correct code.
- **Not a product.** There is no support and no upgrade path except your own.

## Getting started

You need a host that runs Docker, with enough memory or VRAM for the model (see [Hardware](#hardware)). Home Assistant is only needed for voice, and a domain name only if you want to reach Novak from outside your home.

On Unraid (the tested reference):

```bash
git clone https://github.com/almadon/novak.git /mnt/cache/appdata/Novak/repo
cd /mnt/cache/appdata/Novak/repo
./scripts/bootstrap-unraid.sh      # as root: puts `novak` on PATH, survives reboots
novak up                           # seeds the config and tells you what is missing
novak secret set <VAR>             # once for each secret it lists
novak status                       # says what is still unconfigured, and the command to fix it
```

On macOS, put your passwords in the Keychain, run `./scripts/bootstrap-admin.sh --service-user novak` from an admin account, then `./scripts/bootstrap.sh` as the account that runs the stack. The tools are prebuilt images from [novak-integracije](https://github.com/almadon/novak-integracije), which you build once.

Those commands are the outline. The real, ordered instructions, with a column for each platform where a step differs, are in the [deploy checklist](docs/deploy-checklist.md). `novak status` is the quickest way to see where you are (see the [CLI reference](docs/cli.md)).

## How it fits together

| Layer | What runs | Does |
|---|---|---|
| Clients | Open WebUI, Home Assistant, coding agents, Konzol | Where people talk to Novak and manage it |
| Model path | The router (LiteLLM) and the engine (Ollama or oMLX) | Adds the persona, names the roles (`chat`, `deep`, `task`, `ha-voice`) and runs the model |
| Tool path | The gateway | One MCP endpoint that knows who is asking, filters tool lists, holds removals for a yes and keeps the audit log |
| Tools and memory | Hindsight, Outline, Tududi, Home Assistant, search | One MCP server per capability, each with a scoped credential |
| Configuration | `registry/`, `prompts/`, the reconciler | Declared in git and applied by something simple, so git is the audit trail |

New capabilities arrive as tools the assistant can call, not as features bolted into one interface, so every client gets them at once. Powerful tools are allowed, but the ones that can change your system or act irreversibly have to be switched on deliberately. The registry records what a tool can do, who agreed to it and when.

### The console

Konzol is the web console, and it lives in [console/](console/README.md). It is optional: everything it does can be done by editing a file. It shows what Novak has been doing today, lists pending approvals, lets a person browse their own memories and ask to forget one, and shows profiles. It reads from the gateway and writes nothing on its own authority. When it asks for a change, the person confirms on their phone before anything happens.

### Where things run

One host runs the whole stack: the model, memory, voice, chat frontend and console. The only thing that is ever a separate machine is the reverse proxy that terminates TLS, and nothing in Novak's own containers is port-forwarded.

| | Runs | Reachable from |
|---|---|---|
| **The Novak host** | Everything above | Your network and Tailscale only |
| **A reverse proxy** (yours: a VPS, a box on the LAN, whatever you already run) | TLS, and optionally public access to the chat frontend alone | The public internet, if you choose to expose anything |

The proxy reaches the host over [Tailscale](https://tailscale.com) or plain LAN. Tailscale traffic is already encrypted. Traffic across your local network is not, so [docs/proxy.md](docs/proxy.md) covers putting HTTPS in front of these services. The chat interface is built to face the internet. The model server and memory service are not, because they assume everyone talking to them is friendly. [docs/architecture.md](docs/architecture.md) has the full placement reasoning.

### Hardware

| Platform | Engine | Status |
|---|---|---|
| Linux (Unraid 7.x), AMD GPU (RDNA3/4, Vulkan) | Ollama | **Tested.** The household deployment. Measured throughput is in [docs/ollama-settings.md](docs/ollama-settings.md). |
| macOS, Apple Silicon | oMLX | **Tested.** The original deployment, which ran for months on a Mac mini M4 with 24 GB. It is now kept for oMLX development. See [docs/omlx-settings.md](docs/omlx-settings.md). |
| Linux, NVIDIA GPU | Ollama | Untested here. Ollama supports CUDA and nothing in the stack assumes AMD. |
| Linux, CPU only | Ollama | Untested here. Expected to work slowly, with small models only. |
| Linux, not Unraid | Ollama | `docker-compose.yml` is plain Docker. Only the CLI's host wiring in `scripts/bootstrap-unraid.sh` is Unraid-specific, so on another host set `NOVAK_HOME` by hand and skip that script. Untested as a full deployment. |

Running somewhere not in this table is fine, and the design allows it ([docs/engines.md](docs/engines.md)). Treat it as unverified until you have measured it.

## What state is this in?

| Part | State |
|---|---|
| The design and the reasoning | Settled and written down |
| Linux, Unraid and Ollama | In daily use as the household deployment since late August 2026, and it came back unaided from a real reboot (decision #37) |
| macOS and oMLX | Ran for months of real daily use, now kept for development |
| The `novak` CLI on Unraid | Verified end to end against a real host (decision #35) |
| Identity, the gateway and approvals | In use by two people and a household, but only days old, so verified a few times and not yet trusted (see [docs/STATE.md](docs/STATE.md)) |
| The console | Today, Approvals, Memory and Profiles are real pages. People, Health and Logs are still to come |
| A deliberate power-cut test | Not done yet |
| Everything else | Other people's software, configured but not tested here |

Anything marked `VERIFY` in a file is something that could not be checked without the actual hardware.

## Documentation

| Read | For |
|---|---|
| [docs/STATE.md](docs/STATE.md) | What is true right now and what is open. Read first if picking this up. |
| [docs/deploy-checklist.md](docs/deploy-checklist.md) | The real setup instructions |
| [docs/how-memory-works.md](docs/how-memory-works.md) | What "memory" means here, in plain language |
| [docs/what-sets-novak-apart.md](docs/what-sets-novak-apart.md) | Why it is built this way, and what that costs |
| [docs/architecture.md](docs/architecture.md) | How the pieces fit and why each is where it is |
| [docs/identity.md](docs/identity.md), [docs/gateway.md](docs/gateway.md) | One person, their own credentials everywhere, and the gateway that enforces it |
| [docs/security.md](docs/security.md) | Secrets, permissions and what the risks actually are |
| [docs/decisions.md](docs/decisions.md) | Every significant choice, with reasoning and cost |
| [docs/cli.md](docs/cli.md) | Every `novak` command, and how secrets are classified |
| [docs/home-assistant.md](docs/home-assistant.md), [docs/wakeword.md](docs/wakeword.md) | Voice setup, and teaching it "Hey Novak" |
| [docs/engines.md](docs/engines.md), [docs/ollama-settings.md](docs/ollama-settings.md), [docs/omlx-settings.md](docs/omlx-settings.md) | Choosing and tuning the inference engine |
| [docs/proxy.md](docs/proxy.md) | TLS in front of the services |
| [docs/headless-operation.md](docs/headless-operation.md) | Running without a keyboard: how the host comes back after a reboot or a power cut |
| [docs/macos.md](docs/macos.md) | Novak on macOS: what differs on Apple Silicon, including the FileVault trade-off |
| [docs/credits.md](docs/credits.md) | Whose software this is built from, and under which licences |
| [docs/README.md](docs/README.md) | The full index |

## Related repositories

| | |
|---|---|
| **novak** (this one) | The stack: what runs, how it is configured, and why. It includes the console. |
| [novak-integracije](https://github.com/almadon/novak-integracije) | Tools and adapters, for the cases where a service has no MCP endpoint of its own |
| [novak-konzol](https://github.com/almadon/novak-konzol) | The console's old home. Its code and history moved into [console/](console/README.md), and the repository is due to be archived (VERIFY: not done yet). |

## Contributing

Work follows the [conformIT](https://github.com/almadon/conformIT) engineering standard. Conventions for people and agents are in [AGENTS.md](AGENTS.md), and commits are checked by a hook (see [docs/commit-style.md](docs/commit-style.md)).

## Licence

[MIT](LICENSE). What this repo runs is other people's work too. See [docs/credits.md](docs/credits.md) for what each dependency is licensed under, since several are copyleft or otherwise conditional.
