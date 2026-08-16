# Novak Console

A web view over the Novak services layer: per-user profiles (persona, memories,
attached tools) and an admin surface for the MCP/plugin catalog.

This exists because of the *second half* of the repo's non-goal:

> No custom web frontend. … **Build UI only for things chat can't express, and
> build it as a view over these same services.**

Memory browsing, persona editing, and plugin configuration are things chat can't
express. Everything here is a view over oMLX / OpenMemory / Outline / the MCP
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
reconciler/reconcile.sh    (runs on host, no network listener, no user input)
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
(see [../docs/security.md](../docs/security.md), Rule 1). The console can show
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
including the OpenMemory `user_id`. The console does not maintain its own user
table, passwords, or roles. One identity across Open WebUI, the console, and
memory.

### 5. This changes docs/security.md Rule 4

Rule 4 currently states *"Open WebUI is the only multi-user surface."* That is no
longer true once this ships. Update it, and keep the console LAN/Tailscale-only
like everything else.

## Known open items

- **OpenMemory multi-user is unverified.** The stack currently pins a single user
  (`OPENMEMORY_USER`, `NEXT_PUBLIC_USER_ID`). Whether the OpenMemory API supports
  listing/filtering by arbitrary `user_id` needs confirming on-host before
  per-person memory views can work. This is the biggest unknown in the design.
- **Pocket ID availability coupling.** Pocket ID runs on a public VPS while Novak
  is LAN-only. A WAN outage locks admins out of a local console. Decide whether a
  break-glass path is wanted.
- **Registry image allowlist** is not implemented. Any admin can point a server at
  any image, which is arbitrary code execution *by an authenticated admin* — the
  same power they'd have with shell access, so it may be acceptable. Add an
  allowlist if you want defence in depth.
- Auth.js v5 is still pre-1.0; pin the version and re-check the API on upgrades.
- The React/UI surfaces are scaffolding. The auth core and reconciler are real.
