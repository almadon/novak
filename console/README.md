# Novak Console

A web view over the [Novak](https://github.com/almadon/novak) services layer: per-user
profiles (persona, memories, attached tools) and an admin surface for the MCP
plugin catalog.

**Status: Today, Approvals, Memory and Profiles are real pages; the rest are still to come.** `.github/workflows/console.yml` typechecks, audits, builds and
publishes the image to `ghcr.io/almadon/novak-konzol` on every change under `console/`. Today it has a
design token layer, the Today page (read-only status from the gateway, see `docs/gateway.md`), the Profiles page and a
placeholder admin page; the plan for what it becomes is the decision at the end of
`docs/decisions.md` ("Konzol is the configuration plane"). The Auth.js v5 (pre-1.0) API surface is still
worth treating as unproven until a real login has been exercised through it.

This code used to be its own repository (`novak-konzol`, now archived); it moved into the main repository
so a change that spans the gateway and the console is one pull request. Its git history came with it.

## Relationship to the rest of the repository

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

Consequences worth remembering:

- **The registry is the stack's**, because it describes what the stack runs. The console edits it over
  the bind mount and never keeps a copy.
- **Catalog changes are commits** in this repository, so the audit trail is git history.
- **The image is built from `console/`** by `console.yml`, and compose references it by digest
  (decision #45). Unlike the Python services, whose code is mounted from the checkout, the console is
  built into its image, so any change under `console/` needs a new image and a new pinned digest.
