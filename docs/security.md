# Security model

The threat model is not network airgap. It's two things: keeping
conversation data off a public model vendor's servers, and avoiding
"OpenClaw-class" operational failures — plaintext credentials readable by
the model or an attacker, over-broad tool permissions, prompt injection via
content the model reads. Everything below serves one of those two.

## Rule 1 — the model gets capabilities, never credentials

API keys live in MCP server environments, never in a prompt. On macOS
they're sourced from Keychain at startup (`scripts/up.sh`); on Unraid,
which has no OS keychain, a real value goes straight into `.env` instead —
both paths land in the same place, an environment variable the container
sees and the model never does. See `novak secret set` in
[cli.md](cli.md) and the platform split in
[deploy-checklist.md](deploy-checklist.md).

The model calls `search_documents`; the Outline token never appears in a
prompt, a chat log, or a memory store.

**Never paste API keys, passwords, or account numbers into chat.** Chats
are logged, summarized into memory, and re-injected into future contexts.
If you catch yourself about to paste a key, the correct move is a new MCP
server (or env var on an existing one) instead.

Add a secret:

```bash
novak secret set OUTLINE_EVERYTHING_API_KEY
```

`novak secret verify` confirms it reads back unattended, without a prompt
hanging boot — see [headless-operation.md](headless-operation.md) for why
that check exists.

## Rule 2 — least privilege per integration

- One token per integration, scoped as tightly as the service allows;
  read-only unless writing is the point.
- Destructive operations disabled by default. The registry itself carries
  a risk level per MCP server (`registry/mcp-servers.yaml`) — `dangerous`
  entries (e.g. `ha-mcp`, which can edit Home Assistant's own YAML config)
  ship `enabled: false` and stay that way until someone deliberately turns
  them on, with the reasoning recorded next to the entry.
- When adding a new integration with outward side effects: start
  read-only (search/read). Anything that sends, pays, or deletes gets a
  separate, explicit opt-in — see Rule 3.

## Rule 3 — treat retrieved content as untrusted input

An email, a web page, or a wiki article the model reads can contain
instructions aimed at the model ("forward this thread to..."). Mitigations,
in order of importance:

1. **Capability asymmetry**: reading tools are cheap to grant; *acting*
   tools (send email, pay a bill, delete) must be rare, separate, and
   confirmation-gated. If the model can't send, injected instructions
   can't exfiltrate.
2. **Confirmation gates**: any MCP tool with outward side effects should
   require a confirm parameter or step, and clients should surface it.
3. **Scoped sessions**: don't register a powerful MCP server into every
   client — attach it only to the conversations that need it. The HA
   voice agent in particular should carry the smallest tool set that
   still does its job; voice has no screen to review a confirmation on.

This is also what the persona encodes, not just tooling: `prompts/`
(injected by `router/persona_hook.py` for any client pointed at the
router — decision #21/#23) tells the model itself never to ask for
credentials and to treat retrieved content as data, not instruction. A
client that has silently stopped receiving that persona is a client with
weaker enforcement and nothing about it looks broken — see decision #38,
where exactly this happened, and decision #44, which built a detector
(`novak drift --live`) for the specific failure mode that caused it.

## Rule 4 — nothing is reachable from the internet except what earned it

Every service binds to the LAN or tailnet; the router at home forwards
nothing (decision #15). Being reachable from the internet is a property a
service **earns by being designed for it** — accounts, sessions, rate
limiting, an expectation that strangers will knock. Concretely:

| Service | Public? | Why |
|---|---|---|
| The inference engine (oMLX or Ollama) | **No** | No rate limiting, no quotas. A stranger with the key gets the GPU; the way to take the host down is to ask it to think. |
| Hindsight (memory) | **No** | Holds every person's memories behind one shared bearer token — no per-user identity, no lockout. Deletes are permanent. |
| Konzol (the console) | **No** | Reconfigures the stack by writing the registry. Public access to it is equivalent to a shell. |
| Wyoming wake word | **No** | No authentication by protocol design. Anything that reaches the port can speak to the microphone pipeline. |
| Open WebUI | **Yes** — via its own public-facing proxy, on a separate host from the stack itself | The one client actually built for strangers to reach: accounts, sessions, its own rate limiting. Public because it earned it, not because it was convenient. |

The public path for Open WebUI is a **separate proxy on a separate host**
(decision #15), not the internal Caddy instance that fronts the portal —
see [proxy.md](proxy.md) for the full internal-vs-public split and why a
LAN address instead of a Tailscale address is the one mistake that quietly
turns "internal" into "actually reachable from anywhere on the LAN,
including whatever IoT junk is on it too."

Everything else — memory, the console, wake word, MCP servers — is
Tailscale/LAN-only, and stays that way regardless of how many hosts the
stack spans (decision #28/#33's multi-host reality doesn't change this;
see [proxy.md](proxy.md) for how a service on a second host still reaches
the router privately).

**Multi-user surfaces**, both LAN-only: Open WebUI (accounts and RBAC on,
signup disabled once real users exist) and Konzol (Pocket ID OIDC, admin
functions gated on the `admins.novak` group). `admins.novak` also grants
Open WebUI's own admin role and gates the portal — one group, three
independent enforcement points, each worth checking against a real login
rather than assumed transitive from the others (see STATE.md's Open
VERIFY items).

Hindsight is multi-tenant but not a login surface: each MCP connection is
scoped to one bank by URL, and no tool takes a bank as an argument. Its
API key is a secret like any other — without it, the endpoint is open.

Remote access to anything LAN/tailnet-only goes through Tailscale, never a
port forward.

## Rule 5 — the stores are readable; audit them

- Konzol: review and delete memories, per user, behind Pocket ID.
- Outline: the knowledgebase is a normal wiki — correct it there directly.
- Open WebUI chat logs live in its own Docker volume on whichever host
  runs it (Spire, decision #33). `data/` and `.env` are gitignored; keep
  the repo private regardless of that.

## Backups

The state worth backing up: Docker volumes (Open WebUI, Hindsight's
embedded Postgres, and anything else under `*_DATA_DIR`) plus, on
Apple Silicon deployments, `~/.omlx/settings.json`.

- **macOS**: Time Machine covers OrbStack's volume storage and `~/.omlx`
  as long as it's actually backing up the volumes — verify they appear in
  the backup set after first run, don't assume it.
- **Unraid** (the reference deployment, decision #28/#33): confirm the CA
  Appdata Backup plugin (or equivalent) actually covers `$NOVAK_HOME` and
  wherever `*_DATA_DIR`/`OLLAMA_DATA_DIR` point (decision #33 moved these
  onto bulk storage, separate from the appdata path Compose Manager
  backs up by default) — **not yet confirmed on the reference deployment**
  as of this writing. See the deploy checklist's own backup line for the
  same open item.
