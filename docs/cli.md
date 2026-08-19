# `novak` — CLI reference

One command for everything you touch after setup. It lives at
[`scripts/novak`](../scripts/novak) and is meant to be symlinked onto PATH:

```bash
ln -s "$PWD/scripts/novak" /usr/local/bin/novak
```

Run with no arguments, it prints `status`.

---

## At a glance

| Command | What it does |
|---|---|
| `novak status` | what's configured, what's running |
| `novak doctor` | the same checks, explicitly starting nothing |
| `novak ports` | what's listening, and whether it's reachable |
| `novak config` | every setting, and where its value came from |
| `novak config get KEY` | one setting |
| `novak config set KEY VAL` | edit `.env` in place, preserving comments |
| `novak secret list` | which secrets exist — never their values |
| `novak secret set KEY` | store one, prompting without echo |
| `novak secret set KEY --generate` | generate and store one, never displaying it |
| `novak secret show KEY` | print one, for pasting into a client |
| `novak up` | apply config and start |
| `novak down` | stop, keep data |
| `novak restart [SERVICE]` | restart everything, or one service |
| `novak logs [SERVICE]` | follow logs |
| `novak registry` | what the reconciler thinks it should start |

---

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

**Internal** — `CONSOLE_AUTH_SECRET`, and anything else in neither list.

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
