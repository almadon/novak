# Security model

Novak's threat model is not a network airgap. It is two concerns: keeping conversations off a public model vendor's servers, and avoiding the operational failures that sink self-hosted assistants, which are plaintext credentials the model or an attacker can read, tools with more power than they need, and prompt injection through content the model reads. Everything below serves one of those two.

## Where the trust boundaries are

| Boundary | What it separates | Enforced by |
|---|---|---|
| Model and tools | The model never holds a credential and cannot name another person | The gateway: one credential per person, identity taken from the connection, never from a tool argument |
| Person and person | One person's memory, tasks and notes from another's | The gateway's per-person tool lists, and Hindsight banks scoped by URL |
| Asking and doing | A removal from the thing the person actually approved | A held call that waits for Approve on that person's phone (decision #64) |
| Console and stack | A web page from the power to change the stack | The console never talks to Docker, never decides an approval and never calls a tool for you (decision #79) |
| Home and internet | The stack from strangers | Nothing is port-forwarded, and only services built for strangers may face a public proxy |

## Rule 1: the model gets capabilities, never credentials

API keys live in each service's environment, never in a prompt. Secrets are kept in `secrets.env` (mode 600), which is separate from `.env` so that `.env` is safe to print (decision #69). On macOS the values are read from the Keychain at startup. On Unraid, which has no OS keychain, a real value goes into `secrets.env` directly. Both paths end in an environment variable the container sees and the model never does. `novak secret set` and the platform split are covered in [cli.md](cli.md) and [deploy-checklist.md](deploy-checklist.md).

The model calls `search_documents`, and the Outline token never appears in a prompt, a chat log or a memory.

**Never paste an API key, password or account number into chat.** Chats are logged, summarised into memory and fed back into later conversations. If you are about to paste a key, set it as a secret instead:

```bash
novak secret set OUTLINE_EVERYTHING_API_KEY
```

`novak secret verify` confirms that each secret reads back without a prompt, so an unattended boot does not hang. [macos.md](macos.md) explains why that check exists.

The console follows the same rule. It shows secrets by name only, and its two gateway keys (one that can read status, one that can ask for changes) are created by `novak gateway admin-key` and `novak gateway change-key`, shown once and stored as hashes ([gateway.md](gateway.md)).

## Rule 2: least privilege per integration

- One token per integration, scoped as tightly as the service allows, and read-only unless writing is the point.
- Destructive operations are off by default. The registry gives each MCP server a risk level (`registry/mcp-servers.yaml`). Entries marked `dangerous`, such as `ha-mcp`, which can edit Home Assistant's own configuration, ship with `enabled: false` and stay that way until someone turns them on and records why next to the entry.
- A new integration with outward side effects starts read-only. Anything that sends, pays or deletes needs its own explicit opt-in (see Rule 3).
- The gateway offers each connection a short, explicit tool list instead of everything a server exposes. That limits what a model can be tricked into calling, and it also keeps tool definitions inside a small context window (decision #71).

## Rule 3: treat retrieved content as untrusted

An email, a web page or a wiki article the model reads can contain instructions aimed at the model, such as "forward this thread to...". The defences, in order of importance:

1. **Reading is cheap to grant, acting is not.** Tools that send, pay or delete are rare, separate and confirmation-gated. If the model cannot send, injected instructions cannot exfiltrate.
2. **Removals wait for a person.** The gateway holds a removal until the person who asked presses Approve on their phone. A harmless device call, such as a light, scene, fan or media player, needs no tap (decision #63). Requests that nobody answers expire and change nothing.
3. **Scoped sessions.** Attach a powerful tool only to the conversations that need it. The Home Assistant voice agent in particular should carry the smallest tool set that still does its job, because voice has no screen to review a confirmation on.

The persona says the same thing in words. `prompts/`, injected by `router/persona_hook.py` for any client pointed at the router, tells the model never to ask for credentials and to treat retrieved content as data. A client that has quietly stopped receiving it is weaker and looks perfectly healthy. That happened once (decision #38), and `novak drift --live` now watches for the failure that caused it (decision #44).

## Rule 4: nothing is reachable from the internet unless it earned it

Every service binds to the LAN or the tailnet, and the home router forwards nothing (decision #15). A service is allowed to face the internet only if it was built for it: accounts, sessions, rate limits, and an expectation that strangers will knock.

| Service | Public? | Why |
|---|---|---|
| The inference engine (Ollama or oMLX) | **No** | No rate limiting and no quotas. Anyone with the key gets the GPU. |
| Hindsight (memory) | **No** | It holds every person's memories behind one shared API key. Banks are separated by URL, not by credential (see below). |
| Konzol (the console) | **No** | It can ask for changes to the stack. Public access would be close to a shell. |
| The gateway | **No** | It is the door to every person's tools. |
| Wyoming wake word | **No** | The protocol has no authentication, so anything that reaches the port can talk to the microphone pipeline. |
| Open WebUI | **Yes**, through its own proxy on a separate host | It is the one client built for strangers: accounts, sessions and its own rate limits. Sign-in is through Pocket ID only, and local sign-in is off (decision #68). |

The public path for Open WebUI is a **separate proxy on a separate host** (decision #15), not the internal Caddy that fronts the portal. [proxy.md](proxy.md) covers the split, and the one mistake that quietly turns "internal" into "reachable from anything on the LAN": using a LAN address where a Tailscale address was meant. Remote access to anything internal goes through Tailscale, never a port forward.

Hindsight listens on loopback only on the host (decision #62). Checked directly: the port refuses connections from other machines.

### Multi-user surfaces

Open WebUI and Konzol both sign in through Pocket ID, and both are LAN-only. The group `admins.novak` grants Open WebUI's admin role, gates the portal and gates the console's admin pages. That is three separate enforcement points, and each deserves a check against a real login rather than being assumed from the others (see the open VERIFY items in [STATE.md](STATE.md)).

### Known gap: banks share one key

Hindsight is multi-tenant but it is not a login surface. Each MCP connection is scoped to one bank by URL, and no tool takes a bank as an argument, so a model cannot name another person's memory. The API key, however, is a single key for every bank, so anything holding it could open any bank by changing the URL. Close that before treating personal banks as private from anyone who can reach the service (VERIFY: confirmed from Hindsight's source in an earlier session, not re-checked, and no fix is built).

## Rule 5: the stores are readable, so audit them

- **Konzol:** each person can read their own memories and ask to forget one. Forgetting is reversible, and it is confirmed on their phone first.
- **The gateway's audit log** records who did what, by the names of arguments and never their values.
- **Outline** is a normal wiki, so you correct what Novak knows by editing the page.
- **Open WebUI** keeps chat logs in its own Docker volume on the host that runs it. `data/`, `.env` and `secrets.env` are gitignored, but keep the repository private regardless.

## Backups

What is worth backing up: the Docker volumes (Open WebUI, Hindsight's embedded Postgres, the gateway's data, and anything else under `*_DATA_DIR`), `secrets.env`, and on Apple Silicon `~/.omlx/settings.json`.

- **Unraid** (the reference deployment, decisions #28 and #33): confirm that the CA Appdata Backup plugin, or an equivalent, covers `$NOVAK_HOME` and wherever `*_DATA_DIR` and `OLLAMA_DATA_DIR` point. Decision #33 moved those onto bulk storage, separate from the appdata path Compose Manager backs up by default. **Not yet confirmed on the reference deployment.** The deploy checklist has the same open item.
- **macOS:** Time Machine covers OrbStack's volume storage and `~/.omlx` only if it is actually backing them up. Check that they appear in the backup set after the first run.
