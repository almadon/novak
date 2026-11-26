# Konzol, the Novak console

**A web console for Novak: see what the assistant did today, browse your own memories, and confirm changes from your phone.**

> **Status: in testing.** Today, Approvals, Memory and Profiles are real pages in daily use on one deployment. People, Health and Logs are still to come. The Auth.js v5 API is pre-1.0, so treat it as unproven beyond the sign-in this deployment actually exercises.
> This project comes with no warranty or guarantee of fitness for any purpose. Use it at your own risk.
>
> **LLM use.** Built with substantial AI assistance (Claude Code). Design and review are by a human. See [AGENTS.md](../AGENTS.md).

## What this does

Konzol is a Next.js app that signs people in through Pocket ID and shows each of them their own slice of Novak. It reads from two places on the server: the gateway (for what happened today and what is waiting for approval) and Hindsight (for memories).

It does not hold power of its own. When a person asks it to do something, such as forgetting a memory, it sends the gateway a request, the gateway sends Approve and Deny to that person's phone, and nothing happens until they press Approve. The console never talks to Docker, never decides an approval and never calls a tool on someone's behalf. Secrets appear by name only.

| Page | Shows |
|---|---|
| Today | Calls, approvals and failures for today, in plain words |
| Approvals | What is waiting, and what was decided recently, with a way to ask for a test notification |
| Memory | Your own memories (and the household's, if you are an admin), with a request to forget one |
| Profiles | Persona and attached tools per person |
| Appearance | Colour scheme, light or dark, text size, contrast and motion, per device |
| Admin | The tool catalog, over the registry files. A placeholder for now |

## Accessibility

The console follows the device's light or dark and reduced-motion settings until someone overrides them on the Appearance page, which also offers four text sizes, high contrast and a choice of colour scheme. Every scheme, including ones you add, has to pass a contrast test. There is no "larger marks" option, because the console has no small data marks. Buttons, page links and form controls are at least 44px tall.

**Tested:** the contrast test over the built-in schemes; five pages at 320, 390, 768 and 1280px wide with the largest text, checked for sideways scrolling and, at 320px, for small controls. That was one manual run in one browser with made-up data. **Not tested:** 200% browser zoom, a phone in landscape, keyboard-only use, a screen reader, other browsers. There is no automated viewport test yet.

## Use cases

- Checking on your phone, over breakfast, what the assistant did yesterday and whether anything needs your yes.
- Reading what Novak remembers about you and asking it to drop one thing, without editing a database.

## Getting started

The console is a service in the Novak stack, so you rarely run it alone. To work on it:

```bash
cd console
npm ci
npm run typecheck && npm test
npm run dev                      # http://localhost:3002
```

Sign-in needs `OIDC_ISSUER`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` (any OpenID Connect provider works, Novak uses Pocket ID). The status pages need the gateway keys and `GATEWAY_URL`. In a deployment, `novak gateway admin-key` and `novak gateway change-key` create those keys, show each one once and store only a hash. See [docs/gateway.md](../docs/gateway.md) for the two keys and what each is allowed to do.

## How it relates to the rest of Novak

The console is an optional client. The stack runs without it, and everything it does can be done by editing a file under `registry/`.

```
 browser ──▶ Konzol ──▶ gateway   status in (read key), change requests out (change key)
                │          │
                │          └──▶ Supernotify ──▶ your phone ──▶ Approve / Deny
                │
                └──▶ Hindsight   memories, read on the server
```

- **The registry belongs to the stack.** The console edits it over a bind-mounted directory (`REGISTRY_DIR`) and keeps no copy. Catalog changes are commits, so git history is the audit trail.
- **The image is built from this folder.** `.github/workflows/console.yml` typechecks, audits, builds and publishes it to `ghcr.io/almadon/novak-konzol` on every change here. The compose file pins that image by digest (decision #45), so a change under `console/` needs a new image and a pin pull request.
- **Who sees what is decided in one place**, `src/lib/memory.ts`. An admin sees the household's memories and never another person's.

## Documentation

| Read | For |
|---|---|
| [DESIGN.md](DESIGN.md) | Themes, type and layout, why, and how to extend them |
| [docs/gateway.md](../docs/gateway.md) | The status endpoint, the change endpoint and the keys |
| [docs/decisions.md](../docs/decisions.md) | "Konzol is the configuration plane" and the decisions around it |
| [docs/security.md](../docs/security.md) | Trust boundaries |
| [docs/STATE.md](../docs/STATE.md) | What is true right now |

This code used to be its own repository, `novak-konzol`, and its history came with it.

## Licence

[MIT](../LICENSE).
