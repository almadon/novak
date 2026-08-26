# Novak documentation

Everything explanatory lives here. Two kinds of file sit outside this
directory on purpose:

- [`prompts/`](../prompts/novak-chat.md) — the assistant's personas. Those are
  **content the system uses**, not documentation about it, and something will
  eventually read them to configure clients.
- [`registry/`](../registry/mcp-servers.yaml) — declarative inputs the
  reconciler applies. Same reasoning: data, not prose.

## Start here

| | |
|---|---|
| [Where this got to](STATE.md) | Current state and open problems. **Read first if picking this up.** |
| [Deploy checklist](deploy-checklist.md) | The real setup instructions, in the order you do them |
| [How memory works](how-memory-works.md) | What "memory" actually means, in plain language |
| [What sets Novak apart](what-sets-novak-apart.md) | Why build it this way, and what it costs |
| [CLI reference](cli.md) | Every `novak` command |

## Going deeper

| | |
|---|---|
| [Architecture](architecture.md) | How the pieces fit, and why each is where it is |
| [Decisions](decisions.md) | Every significant choice, with reasoning and cost |
| [Security](security.md) | Secrets, permissions, and what the risks actually are |
| [Running headless](headless-operation.md) | Unattended restarts, and the FileVault trade-off |

## Setting up the parts

| | |
|---|---|
| [oMLX settings](omlx-settings.md) | Which models, how to tune them, and the profiles |
| [Memory setup](memory-setup.md) | Standing up the memory backend |
| [Home Assistant](home-assistant.md) | Voice setup |
| [Reverse proxy](proxy.md) | TLS on the LAN, using a proxy you already run |
| [Wake word](wakeword.md) | Teaching it to answer to "Hey Novak" |

## Conventions

| | |
|---|---|
| [Commit style](commit-style.md) | Conventional Commits, enforced by a hook |
| [Credits](credits.md) | Whose software this is built from |
| [conformIT audit](conformit-audit.md) | Where Novak diverges from the shared engineering standard |
