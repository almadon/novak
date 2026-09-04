# `novak` — CLI reference

One command for everything you touch after setup. It lives at
[`scripts/novak`](../scripts/novak). `bootstrap.sh` symlinks it onto PATH at
`~/.local/bin/novak`, not `/usr/local/bin`: the service account has no sudo,
and `/usr/local/bin` needs root to write to. A stale `/usr/local/bin/novak`
symlink from an old checkout path is also unfixable by this account, since
removing it needs root too, which is what happened on the mini after the
repo moved and is why `~/.local/bin` (writable, and already earlier on PATH)
is the answer rather than a workaround.

If you ever need to link it by hand:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/scripts/novak" ~/.local/bin/novak
```

Run with no arguments and it opens an interactive menu instead of printing
`status` — see [The menu](#the-menu) below. Every command in this reference
still works exactly as shown when typed directly; the menu is a second way
in, not a replacement for scripting against these.

## Unraid (decision #35)

Every command in this reference works the same way on Unraid — same
`novak adopt`, same `novak drift`, same `novak status`. Two things differ,
both because the platform genuinely has no equivalent, not by choice:

- **Where it's linked from.** `scripts/bootstrap-unraid.sh` (run once, as
  root, after cloning the repo) symlinks it at `/usr/local/bin/novak` and
  adds a line to `/boot/config/go` to re-create that symlink on every boot
  — required on Unraid specifically, since `/usr/local/bin` sits on a
  RAM-based overlay rebuilt from the flash image at each boot, unlike a
  normal Linux root filesystem. It also writes `NOVAK_HOME` to
  `/boot/config/novak/novak_home`, since `$HOME` (`/root`) is not a safe
  default the way it is on macOS — Unraid's Compose Manager plugin always
  derives its own project directory from wherever `docker-compose.yml`
  lives, so `NOVAK_HOME` has to be that exact path.
- **Where secrets live.** No OS keychain exists to use headlessly on
  Unraid — there's no logged-in desktop session to unlock one. `novak
  secret set` writes the real value directly into `.env` instead (protected
  by file permissions, 600, checked by `novak secret verify`) rather than
  the macOS Keychain. This is a genuinely lower security bar, not a
  disguised equivalent — see [`scripts/lib/secrets.sh`](../scripts/lib/secrets.sh)
  for the reasoning. Every other command that touches a secret (`config`,
  `status`, `omlx apply`'s `OMLX_API_KEY` read, the checklist's live probes)
  goes through the same abstraction and needs no per-platform handling.

`novak omlx apply` refuses outright on Linux (oMLX is Apple Silicon only);
everything else — including `novak router apply` for Ollama/engines.yaml —
works identically on both platforms.

---

## At a glance

| Command | What it does |
|---|---|
| `novak` | interactive menu — everything below, no arguments needed (aliases: `menu`, `tui`) |
| `novak status` | what's configured, what's running |
| `novak doctor` | the same checks, explicitly starting nothing |
| `novak ports` | what's listening, and whether it's reachable |
| `novak config` | every setting, and where its value came from |
| `novak config get KEY` | one setting |
| `novak config set KEY VAL` | edit `.env` in place, preserving comments |
| `novak secret list` | which secrets exist — never their values |
| `novak secret set KEY` | store one, prompting without echo |
| `novak secret set KEY --generate` | generate and store one, never displaying it |
| `novak secret verify` | do they read back unattended, or would a prompt hang boot? |
| `novak secret show KEY` | print one, for pasting into a client |
| `novak up` | apply config and start |
| `novak update [SERVICE...]` | pull new images and recreate what changed |
| `novak down` | stop, keep data |
| `novak restart [SERVICE]` | restart everything, or one service |
| `novak logs [SERVICE]` | follow logs |
| `novak registry` | what the reconciler thinks it should start |
| `novak drift` | where this deployment differs from the repo (aliases: `verify`, `check`) |
| `novak omlx apply` | apply `registry/omlx.yaml` — models, profiles, TTLs |
| `novak router apply` | apply `registry/engines.yaml` -> `router/config.yaml` (decision #28); needs `novak restart router` after |

---

## The menu

Run `novak` with no arguments (or `novak menu`, `novak tui`, identical) and
you get this instead of a `status` printout:

```
 1) Status
 2) Ports
 3) Drift / verify
 4) Guided setup — configure what's missing
 5) Deployment checklist — phase by phase, with live checks
 6) Config — view or change a setting
 7) Secrets — view, set, or verify one
 8) Registry — MCP servers the reconciler sees
 9) oMLX — apply models and profiles
10) Stack — up / update / down / restart / logs
11) Quit
```

No new dependency for this. [gum](https://github.com/charmbracelet/gum) was
tried first, since it already solves "menu in a shell script" well —
installing it failed here, because this account has no write access to
`/opt/homebrew`, the same class of problem `bootstrap.sh`'s CLI-symlink and
LaunchAgent fixes exist to avoid. A brew-installed binary as a hard
dependency of the CLI's *default* invocation would reintroduce that for
every fresh deployment, so the menu is plain `read` and `case`: nothing to
install, works the moment `bootstrap.sh` has run.

Every entry runs the same command you'd type directly — the menu is a
second way in, not a separate implementation. Numbers 1, 2, 3, 8 just call
`status`/`ports`/`drift`/`registry`; the rest ask a short follow-up question
(which key, generate or paste, which service) and then call `config`,
`secret`, `omlx`, or the stack commands the same way.

### Guided setup (4)

Walks through whatever `novak status` would otherwise just list as missing,
asking for each value instead of making you go run the command yourself. If
the repo has added settings this deployment's `.env` doesn't have yet (check
`novak drift` reports this too), it offers to adopt them first — refuse and
anything needing one of those lines reports "Unknown setting" instead of
prompting, same as running `config set` on an unrecognized key directly
would.

Required settings and secrets first, then the console and the portal as
separate opt-in passes — each one is a real yes/no question, not assumed
from being present in the menu.

### Deployment checklist (5)

A phase-by-phase read-through of
[deploy-checklist.md](deploy-checklist.md), pausing between phases. Where a
step is something this CLI can actually check — a file present, a port
answering, a process running — it runs that check and reports pass or fail,
rather than just repeating the markdown. Where the step is inherently
manual (clicking through Pocket ID's own admin UI, downloading a model
file), it prints the instruction and asks you to confirm you did it.

Nothing here is saved between runs. It's a guided walk with real checks
where checks are possible, not a persisted checklist — rerun it any time to
recheck everything from the top.

Two of its checks are worth knowing about because they were wrong on the
first pass and are recorded here rather than quietly fixed: the oMLX check
originally sent no API key and didn't handle a non-2xx response, so an
`API key required` error looked identical to "reachable, no models loaded."
The Hindsight check originally sent a bare `GET`, which Hindsight answers
with `200 {}` regardless of authentication — a handshake response, not a
tool call — so it read as "wide open" when a real unauthenticated tool call
correctly gets refused with 401. Both were reproduced directly against the
running stack before being fixed, which is the reason to trust the numbers
this reports over a first instinct about what a health check like this
"should" do.

## Where things live

The checkout holds definitions; `$NOVAK_HOME` (default `~/.novak`) holds this
deployment. That split is why `git pull` never fights a running stack.

```
~/.novak/.env                        settings          novak config
~/.novak/registry/mcp-servers.yaml   which MCP servers  edit by hand or via the console
macOS Keychain, as novak/<VAR>       secrets           novak secret
```

**The Keychain is per-user.** Items added from your admin account are invisible
to `novak`, and this is the single most common reason a secret reads as missing
when you are sure you set it.

---

## Configuration

```bash
novak config                 # every setting, and where the value came from
novak config get HOST_NAME
novak config set OMLX_PORT 8000
```

`config` never prints a secret's value, and `config set` refuses to write one —
it redirects you to `novak secret set`, so a real secret cannot end up in
`.env` by accident.

Changes are not live. `novak up` applies them, and recreates only the
containers whose values actually changed.

---

## Where each kind of setting lives

Three places, and which one you want depends on what the thing *is*. This trips
people up on MCP servers in particular, because the URL and the token do not
live together.

| | Lives in | Example |
|---|---|---|
| Stack settings | `~/.novak/.env` | `HOST_NAME`, `OMLX_PORT` |
| Secrets | macOS Keychain | `HINDSIGHT_API_KEY` |
| **URL of an `external` MCP server** | **`registry/mcp-servers.yaml`** | Tududi, Outline, Hindsight |
| URL of a `container` MCP server | `.env` | `VIKUNJA_URL`, `HA_MCP_URL` |

**There is no `TUDUDI_URL`, and that is not an omission.** Tududi is an
`external` entry — something already running elsewhere that Novak only points
clients at — so its address is the `url:` field in the registry:

```yaml
  - name: tududi
    kind: external
    url: https://tududi.example.tld/api/mcp
    auth: TUDUDI_API_TOKEN      # the NAME of a Keychain item, not a value
    enabled: false
```

Edit the URL there, in `$NOVAK_HOME/registry/mcp-servers.yaml`, and set the
token with `novak secret set TUDUDI_API_TOKEN`. Then flip `enabled: true`.

A `container` entry is the other case: Novak runs it, so it needs both halves
as variables — `VIKUNJA_URL` and `VIKUNJA_API_TOKEN`. The reconciler skips a
container entry whose variables are unset and says which ones, so an
unconfigured integration never blocks the rest.

`auth:` in an external entry is **informational**. Nothing injects it — the
token goes into the *client's* registration, as an Authorization header. It is
recorded so the registry can answer "what do I need to wire this up".

### When a reverse proxy is in front

`HOST_NAME` is how machines in this stack reach each other. It is **not** how a
person reaches a service through a proxy — that name lives on another host and
nothing here can discover it. Set it explicitly:

```bash
novak config set OWUI_PUBLIC_URL https://cas.example.tld
novak config set KONZOL_PUBLIC_URL https://konzol.example.tld
```

Blank means "no proxy, use `HOST_NAME`", which is right for direct access.

This is worth getting right because it fails *softly*. Open WebUI derives its
OIDC callback from the incoming request's Host header when nothing pins it, so
a login started at one hostname returns you to whichever name you happened to
type — and every such name is a separate redirect URI the IdP must have
registered. The symptom is being bounced to a URL you never asked for rather
than an error. Setting `OWUI_PUBLIC_URL` pins both the site URL and the
callback, leaving one URI to register.

Check what a service actually ended up with:

```bash
docker compose config | grep -E 'WEBUI_URL|OPENID_REDIRECT_URI'
```

### Signing in to Open WebUI with Pocket ID

Configured through `.env`, not in Open WebUI's admin panel — it reads these at
startup and has no UI for them:

```
OWUI_OIDC_ISSUER=https://<pocket-id-host>/.well-known/openid-configuration
OWUI_OIDC_CLIENT_ID=...
novak secret set OWUI_OIDC_CLIENT_SECRET
```

Note the issuer is the **discovery document**, not the bare issuer URL, and
this needs a **second Pocket ID client** separate from the console's, because
the redirect URI differs: `http://<HOST_NAME>:3000/oauth/oidc/callback`.

Leave them unset for local accounts. OAuth turns on only when client id, secret
and provider URL are all present.

## Secrets

Three kinds, because who else knows the value decides how you may set it.

**Externally owned** — `OMLX_API_KEY`, `OIDC_CLIENT_SECRET`,
`OUTLINE_EVERYTHING_API_KEY`, `VIKUNJA_API_TOKEN`, `TUDUDI_API_TOKEN`.

The value must *match* what another system already holds. `--generate` is
**refused** here, deliberately: a fresh random value is not a shortcut, it is an
outage that looks like a permissions problem.

```bash
novak secret set OMLX_API_KEY      # paste the value from oMLX's own settings
```

**Shared** — `HINDSIGHT_API_KEY`.

We generate it, but Open WebUI and Home Assistant each register the MCP endpoint
using it as a bearer token. Generating is fine; rotating it means re-registering
every client that held the old one, and `secret set` says so when you do.

```bash
novak secret set HINDSIGHT_API_KEY --generate
novak secret show HINDSIGHT_API_KEY     # then paste into each client
```

**Internal** — `CONSOLE_AUTH_SECRET`, `WEBUI_SECRET_KEY`, and anything else in
neither list.

One container reads it and nobody else ever needs it. Generate it and never look
at it. Rotating costs you nothing but the sessions it signed.

```bash
novak secret set CONSOLE_AUTH_SECRET --generate
```

`novak secret show` is the only command that prints a secret, and only for the
key you name. `list` and `config` never do.

---

## Running

```bash
novak up                 # apply config and start
novak down               # stop, keep data
novak restart hindsight  # one service
novak logs open-webui    # follow
```

`up` is the only thing that applies configuration. It is safe to re-run — that
is the intended way to pick up any change, and it recreates only what changed.

It refuses to start if a required setting or secret is missing, rather than
starting something half-configured. **Optional pieces are not a reason to
refuse.** Anything that only it needs is skipped, with a line saying which
values were missing, and everything else starts:

```
skipped:  vikunja — not configured: VIKUNJA_URL, VIKUNJA_API_TOKEN
skipped:  console — not configured: OIDC_ISSUER, OIDC_CLIENT_SECRET
```

That covers MCP servers (skipped by the reconciler) and the console (gated
behind a compose profile). Set the values and re-run `novak up` to add one
later — nothing else is disturbed.

Only genuinely shared values refuse: `HOST_NAME`, which every service builds
its URLs from, and `HINDSIGHT_API_KEY`, without which the memory endpoint would
be open to anything that can reach the port.

### Updating

Every image in `docker-compose.yml` is unpinned (`:latest`, `:main`), and
`up` never pulls, so a new release sitting on the registry does not reach a
running stack on its own. `update` is the missing half:

```bash
novak update              # pull every image, recreate whatever changed
novak update open-webui   # just one
```

It runs `docker compose pull`, then re-runs `up.sh`, which is what actually
recreates containers, re-applies the MCP registry, and re-applies the oMLX
profiles. That last part matters more than it looks: pulling a newer app
image and skipping the reapply is how a stack ends up running new code
against an old registry. `docker compose up -d` only recreates a container
whose image or config actually changed, so running `update` when nothing
is new is a clean no-op.

Being unpinned cuts both ways. It also means an upstream breaking change
reaches you the next time you happen to run this, with no version to roll
back to. If that becomes a real problem, the fix is pinning digests in
`docker-compose.yml`, which turns an update from an automatic pull into a
deliberate, reviewable edit — worth a decision entry if you go that route,
not a CLI flag.

---

## Checking

`novak status` — what is configured and what is running.
`novak doctor` — identical checks, named for when you want to be sure nothing
starts.

`novak ports` probes each port by connecting, rather than reading sockets:
`lsof` without `sudo` only sees your own processes, so a service run by another
account looks absent when it is merely invisible.

```
SERVICE          PORT   LOCALHOST   100.120.1.110
oMLX (host app)  8000   yes         no
Console          3002   yes         yes
```

Reading that table:

- **both yes** — reachable from other machines.
- **localhost yes, tailscale no** — bound to `127.0.0.1` only. For oMLX that is
  its own `server.host` setting, not anything Novak controls. `HOST_NAME`
  affects no binding anywhere; it only builds URLs.
- **both no** — not running. Try `novak status`, then `novak logs <service>`.

The Tailscale column asks the system daemon by its socket. On macOS a bare
`tailscale` command may answer from a per-user GUI app instead, which can report
`NeedsLogin` while the daemon underneath is perfectly online.

---

## oMLX profiles

```bash
novak omlx apply            # apply registry/omlx.yaml
novak omlx apply --dry-run  # show what would change
```

## Inference engines (decision #28)

```bash
novak router apply            # apply registry/engines.yaml -> router/config.yaml
novak router apply --dry-run  # show what would change
novak restart router          # required after — LiteLLM reads config.yaml
                               # at container start, not on a hot reload
```

See [engines.md](engines.md) for what qualifies as an engine and
[ollama-settings.md](ollama-settings.md) / [omlx-settings.md](omlx-settings.md)
for the two documented today.

Writes oMLX's own JSON files rather than calling its admin API, which would need
a second credential — decision 17. Because oMLX keeps this state in memory and
rewrites it on its own saves, applying **stops oMLX, writes, and starts it
again**, dropping loaded models.

So it diffs first and does nothing when nothing differs. `up.sh` calls it on
every run for that reason, and non-fatally: oMLX is a host app the stack does
not manage, and at boot it may not be up yet. A missing inference server should
no more stop the stack than a missing task tracker.

Unknown field names are **refused**, never dropped — a profile that quietly did
not take is the failure this exists to prevent. The accepted list is read from
the installed oMLX itself, so it tracks the version actually running.

After writing it restarts oMLX and checks the profiles really are served,
rather than assuming. Profiles appear to clients as `<model>:<profile>`:

```
Qwen3-4B-Instruct-2507-4bit:ha-voice
Qwen3-14B-4bit:chat
```

## Drift

`up.sh` seeds `$NOVAK_HOME` once and never overwrites it, because your config
and your registry belong to you. The cost is that a repo-side change never
reaches an existing install, and nothing says so.

That failure is silent by construction: the stack stays healthy, every file
stays valid, and the deployment simply describes an older system. This one ran
for a while on a registry that still listed a memory backend replaced two
migrations earlier — and carried no Hindsight endpoints at all, so nothing
advertised memory to any client. Nothing looked wrong.

```bash
novak drift
```

Compares settings against `.env.example` and the deployed registry against the
repo's, and prints what differs.

```bash
novak drift --adopt
```

Copies settings the repo has added into your `.env`, with the comments that
explain them, and **never touches a value already set** (it backs the file up
first regardless). This matters more than it sounds: `novak config set` only
accepts keys already present in `.env`, so a setting the repo added is
unreachable —

```
$ novak config set OWUI_OIDC_ISSUER https://...
Unknown setting 'OWUI_OIDC_ISSUER'. 'novak config' lists them.
```

— until the file gains the line. Without `--adopt` the only way through is
hand-editing `.env`, which is the interface this CLI exists to replace.

Adopting only adds the lines. Values stay at the repo's defaults until you set
them, and any secrets among them still need `novak secret set`. `novak status` shows a one-line pointer when
the registry differs, since nobody thinks to look for a silent problem.

It is **read-only and credential-free** — it opens two files and prints the
difference, so it is safe to run anywhere and cannot cause the drift it
reports. Adopting the repo's registry is left to you, with the commands
printed, because your local choices get overwritten.

**What it does not check:** client-side configuration. Whether Open WebUI's
model preset or Home Assistant's agent prompt still matches `prompts/` needs
each client's API credentials, which core deliberately does not hold — see
decision 18.

## When something breaks

```bash
novak status            # what's configured, what's running
novak logs <service>    # why a container is unhappy
novak registry          # what the reconciler thinks it should start
novak config            # every setting and where its value came from
```

If a rebuild is easier than a diagnosis, [`scripts/reset.sh`](../scripts/reset.sh)
removes containers and keeps your config, secrets and data. `--purge-data` and
`--purge-config` exist and both ask first.
