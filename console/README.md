# Novak Console

A web view over the [Novak](https://github.com/almadon/novak) services layer: per-user
profiles (persona, memories, attached tools) and an admin surface for the MCP
plugin catalog.

**Status: builds, not yet exercised as a real UI.** CI (`ci.yml`) installs,
builds, and publishes an image to `ghcr.io/almadon/novak-konzol` on every
push to `main` — that much runs. Per the novak repo's `docs/STATE.md`: three
placeholder pages and a design token layer, no real components yet, and
"less urgent now that the portal covers the cross-app viewing want that was
the main pressure on it." The Auth.js v5 (pre-1.0) API surface is still
worth treating as unproven until a real login has been exercised through it.

## Relationship to the novak repo

This is an **optional client** of the Novak stack, not a component of it. The
stack runs without it: `registry/mcp-servers.yaml` over there can be edited by
hand and applied with `reconciler/reconcile.py`, and nothing here is required.

The entire interface between the two repos is **one bind-mounted directory**:

```
novak/registry/   ──bind mount──▶   /app/registry   (this app writes it)
       │
       ▼
novak/reconciler/reconcile.py  ──▶  docker compose up -d
```

That's deliberate. The console never talks to Docker, never calls the
reconciler, and never holds a credential for the stack — it writes a file, and
something else with no network exposure acts on it.

Consequences of the split worth remembering:

- **The registry lives in the novak repo**, because it describes what that
  stack runs. Do not move a copy here.
- **Git history for catalog changes is in the novak repo**, not this one.
- This repo publishes a container image; the novak compose references it by
  tag. It does not build from source across repos.

## Why it exists at all

The novak README says "no custom web frontend." The full sentence also says:
*build UI only for things chat can't express, and build it as a view over these
same services.*

Memory browsing, persona editing, and plugin configuration are things chat
can't express. Everything here is a view over oMLX / Mem0 / Outline / the MCP
servers — the console owns no state that matters. If it disappeared, nothing of
value would be lost, same as Open WebUI.

## Security model

The console is a **multi-user, privileged-looking surface**, so it is built so
that it is not actually privileged.

### 1. The console never touches Docker

This is the load-bearing decision. Mounting `/var/run/docker.sock` into a
web-facing container is root-equivalent: anything that can *create* a container
can create a privileged one with the host filesystem mounted and escape. A
socket proxy can safely whitelist `restart`/`inspect`/`logs`, but **not
`create`** — and creating MCP servers is exactly what the catalog needs to do.

So the write path is GitOps, matching the pattern used elsewhere in the fleet:

```
Console (web, OIDC-gated)
    │  validates schema, writes
    ▼
registry/mcp-servers.yaml  ──git──▶  reviewable history
    │
    ▼
reconciler/reconcile.py    (runs on host, no network listener, no user input)
    │
    ▼
docker compose up -d
```

A total compromise of the console yields *"attacker wrote a YAML file"*, not
*"attacker has root in the container VM."* The reconciler parses a
schema-validated file and never evaluates anything from an HTTP request.

Note on runtime: OrbStack (and Podman on macOS) run containers inside a Linux
VM, so an escape lands in the VM rather than macOS. That boundary is already
present — swapping container runtimes buys much less here than removing the
socket from the web surface does.

### 2. Secrets never enter the registry or the UI

`registry/mcp-servers.yaml` records **which env var names** a server needs, never
their values. Values continue to come from macOS Keychain via `scripts/up.sh`
(see [novak/docs/security.md](https://github.com/almadon/novak/blob/HEAD/docs/security.md), Rule 1). The console can show
that `OUTLINE_API_KEY` is *required and present*; it can never read or display it.

### 3. Admin gating is server-side and re-validated

Admin functions require `admins.novak` in the OIDC `groups` claim from Pocket ID.

- Enforced in **API route handlers**, not just middleware and not in the UI.
  Hiding a button is not access control.
- **Mutating admin operations re-check group membership against Pocket ID's
  userinfo endpoint** rather than trusting the session. Without this, revoking
  someone's admin in Pocket ID would not take effect until their session
  expired — unacceptable for a surface that reconfigures the stack.
- See [src/lib/authz.ts](src/lib/authz.ts). That file is the whole authorization
  story; review it first.

### 4. Identity is shared, not invented

The Pocket ID subject (`sub`) is the primary key for everything per-user —
including the Mem0 `user_id`. The console does not maintain its own user
table, passwords, or roles. One identity across Open WebUI, the console, and
memory.

### 5. This adds a second multi-user surface

The novak stack previously had exactly one place where multiple people could
log in (Open WebUI). This is the second, and it is the one that can reconfigure
things — so keep it LAN/Tailscale-only like everything else.
`novak/docs/security.md` Rule 4 has been updated to say so.

## Known open items

- **Memory backend resolved.** OpenMemory was deprecated upstream; the stack now
  uses Mem0 self-hosted, which supports `user_id` per request. The console calls
  its REST API directly (server-side, admin key), while model clients go through
  [novak-integracije/memory-mcp/](https://github.com/almadon/novak-integracije/blob/HEAD/memory-mcp/README.md). Neither path lets a caller
  name another user.
- **Pocket ID availability coupling.** Pocket ID runs on a public VPS while Novak
  is LAN-only. A WAN outage locks admins out of a local console. Decide whether a
  break-glass path is wanted.
- **Registry image allowlist** is not implemented. Any admin can point a server at
  any image, which is arbitrary code execution *by an authenticated admin* — the
  same power they'd have with shell access, so it may be acceptable. Add an
  allowlist if you want defence in depth. Partly mitigated by risk levels below.
- **The UI does not yet surface risk levels.** The registry supports them and the
  reconciler enforces them, but the admin page doesn't show or edit them. When
  it does, `dangerous` entries should require typing the acceptance rather than
  clicking a toggle — the friction is the feature.
- Auth.js v5 is still pre-1.0; pin the version and re-check the API on upgrades.
- The React/UI surfaces are scaffolding. The auth core is real, but unrun.

## Risk levels ("danger zone")

Each registry entry carries a risk level: `standard`, `elevated`, or
`dangerous`. Anything above `standard` will not start until someone records
what it can do, who accepted it, and on what date. Turning it back off needs
nothing.

This is deliberately not a ban. The goal is that powerful integrations get
enabled on purpose, with a note for whoever reads the repo in six months —
including you. The reconciler reprints accepted risks on every run so they
don't fade into the background.

Enforcement lives in the novak repo's reconciler, not here — this app can
display and edit the levels, but cannot bypass them. See
[novak/registry/mcp-servers.yaml](https://github.com/almadon/novak/blob/HEAD/registry/mcp-servers.yaml) for the
levels and [novak/docs/decisions.md](https://github.com/almadon/novak/blob/HEAD/docs/decisions.md) #10 for the
reasoning.

## Licence

MIT — see [LICENSE](LICENSE).
