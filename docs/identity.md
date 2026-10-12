# Identity: one person, their own credentials everywhere (proposal)

**Status: a proposal, not a decision.** Nothing here is built. It records the
design question, what was checked, and the plan, so the next step is a choice
and not a rediscovery. Items marked VERIFY were not checked.

**Direction confirmed so far (2026-10-12):** a gateway is wanted; a trusted
header from Open WebUI is acceptable as a fallback; each person supplies their
own key for services like Tududi so they act as themselves; satellites go
through the gateway with the household identity. See "Decisions taken" at the end.

## The goal

A signed-in person is the same person in every part of Novak. `tmeuze` sees
Outline, Tududi and memory as `tmeuze`, `ushy` sees theirs, and neither session
can reach the other's data. Shared things (the household bank, voice satellites)
are shared on purpose and said so. One experience, not a different rule per
client.

## Where things stand

The registry says what exists, the reconciler applies it and checks drift, and
the router injects the persona and routes models. None of them knows who is
asking. In particular the router does not apply memory to queries: the model
calls Hindsight's tools when it decides to, and the persona tells it to.

| Piece | Who it thinks you are today |
|---|---|
| Pocket ID | The identity provider (OIDC) |
| Console | Signs in through Pocket ID and maps the person to the bank of the same name. The only place isolation is real |
| Open WebUI | Pocket ID sign-in, separate accounts. MCP tools are admin-registered, each holding one key |
| Home Assistant | Its own accounts. The stock agent sends no user (below) |
| Hindsight | One shared key for every bank. Read from its source: `ApiKeyTenantExtension` checks one key and returns the same schema for all |
| Outline, Tududi | A per-account key, but whichever key a registry entry holds is used by everyone who can see the entry |
| Router | No identity (decision #21 is half built: "a verified identity travels with the request") |

A credential stands in for a person only where a client happens to enforce it.

## Principles

1. A credential belongs to a person, never to a client or a shared entry.
2. Identity is established once (Pocket ID, or a per-person key) and carried.
   It is not re-asserted by whatever is calling.
3. Shared is explicit. Household things are marked shared, and everything else
   is personal.
4. What cannot be identified stays shared. A microphone cannot tell who is
   speaking, so voice satellites use the household identity.

## How each client can carry identity

**Console.** Done.

**Open WebUI.** From its [MCP documentation](https://docs.openwebui.com/features/extensibility/mcp):
only admins register MCP servers, and an admin can limit each one to users or
groups with Access Control. A connection can send custom headers with template
tokens (user id, email, role, groups) filled in per request, or the user's own
SSO access token, or run an OAuth 2.1 grant per user. So Open WebUI can tell a
gateway who is asking. Two caveats: a header is only trustworthy if nothing but
Open WebUI can reach the gateway, and whether the SSO token is accepted
depends on what the gateway checks. VERIFY both against the running version.

**Home Assistant.** The stock `litellm` conversation agent does not pass the
Home Assistant user to the API. Read from its source (`entity.py`): the only
identifying field it sends is `user`, set to the conversation id. So "the HA
username is the Pocket ID username" cannot be done through that agent: the name
never leaves Home Assistant.

What does work, with no username matching: **a pipeline per person.** Each
person gets an Assist pipeline whose agent holds that person's key (or a
per-person URL). Their phone, the app and their browser select that pipeline;
the satellites keep the household one. Identity then comes from which key the
pipeline holds. The trust is the same as the device itself: whoever holds your
phone is you. Home Assistant's MCP client takes a URL and no headers, so a
person's tools there need a per-person URL that carries the credential.

## Pocket ID can be the authorization server

Pocket ID has been adding what MCP's authorization model expects. From its
release notes and tests (checked on GitHub, latest release v2.18.0): API
resources, so a token can be issued for a named resource (an audience); OIDC
clients registered by a client ID metadata document (the MCP client registration
style); RFC 8414 authorization server metadata (v2.14.0); and a grant with no
scopes, which is what MCP clients send. It has also published a
[video on protecting MCP servers with it](https://youtu.be/JjoXz2u5r3Y).
Dynamic client registration was not found. VERIFY which version runs here.

This changes the gateway's job for the better. Instead of trusting a header, the
gateway can be an OAuth-protected MCP resource: a client signs the person in
through Pocket ID, gets a token whose audience is the gateway, and the gateway
checks the signature and reads the person from it. That identity cannot be
claimed by a caller; it has to be issued. It also fits Home Assistant, whose MCP
client speaks OAuth, so a person in the app or web could authenticate to the
gateway as themselves. Open WebUI can do per-user OAuth 2.1 against an MCP
connection. VERIFY how each handles a Pocket ID resource (static versus
dynamic client registration is the likely snag).

A trusted header remains the simpler fallback for Open WebUI, safe only if
nothing but Open WebUI can reach the gateway.

## The gateway

The missing piece, and the right place for this: where identity meets tools and
models. It would:

- authenticate the caller (a Pocket ID token for the audience of the gateway;
  failing that, a trusted header from a known client; for the household, a
  household key),
- map the caller to a person through a small directory,
- present that person's tools only, and add their backend credentials
  (their Hindsight bank, their Outline key, their Tududi key) so no client holds
  them,
- let shared entries (household memory) through for anyone, and
- log who did what (accounting; see below).

It would also close the Hindsight gap: the Hindsight port would be reachable
only from the gateway, which holds the one shared key and decides which bank a
caller may open.

### Three ways to build it

1. **LiteLLM, which already runs as the router.** (It would have to accept
   Pocket ID tokens; whether it does so without a licence is unconfirmed.) Its
   [MCP gateway](https://docs.litellm.ai/docs/mcp) can register MCP servers and
   limit them by key, team or organisation, forward headers, and has per-user
   server variables. A virtual key per person would see only that person's
   servers. Unknowns: it stores servers and keys in a database (Postgres, which
   the stack does not run for it today), the docs fetched do not say which
   features need a licence, and whether the backend credential can stay
   server-side per person is not confirmed. VERIFY all of it with a spike.
2. **A small Novak gateway.** Python, in this repo, doing exactly the list
   above. Full control and no new dependency, at the cost of owning an MCP
   proxy (streamable HTTP, sessions) and being code the project has so far
   avoided writing.
3. **Traefik forward-auth, per bank.** The route already being planned for
   Hindsight. Protects Hindsight only, not Outline or Tududi.

**Recommendation:** spike option 1 first, for half a day: two people, two
Hindsight banks, one test key each, and a Pocket ID token as the credential if
it will take one. If a person's key sees only their own
servers and the backend key never leaves the router, adopt it and have the
reconciler render the MCP servers into the router config. If not, build option
2. Option 3 can still sit in front of the Hindsight port as a second layer.

## Authentication, authorization, accounting

- **Authentication:** who is this. A Pocket ID token (or the fallbacks above).
- **Authorization:** what may they touch. Their own entries, found through the
  directory, plus entries marked shared. Nothing else is listed to them, so
  there is nothing to guess.
- **Accounting:** what did they do. The gateway logs person, tool, backend,
  time and outcome (never arguments or secrets). And because each person's own
  key is used downstream, Tududi and Outline attribute the action to that
  person in their own history as well.

## Personal credentials

A person supplies their own key for each service, so they act as themselves
there. Tududi is meant for shared project work and has private workspaces; the
sharing happens inside Tududi, between accounts, so Novak does not need a
"shared between two people" kind of entry. The gateway only needs each
person's own key.

Those keys have to be stored somewhere only the gateway reads, and entered by
the person. Two ways: an administrator enters them with `novak person` (works
first), or each person pastes their own key into a write-only form (the
console is the obvious place, since it already signs people in, but today it
never handles secrets by design, so that is a decision to take, not an
assumption).

## The people directory

`registry/people.yaml`, a mapping and not an auth system:

```yaml
people:
  tmeuze:
    pocket_id: tmeuze
    hindsight_bank: tmeuze
    entries: [outline-everything, tududi-tui]
  ushy:
    pocket_id: ushy
    hindsight_bank: ushy
    entries: [tududi-ushy]
shared:
  entries: [hindsight-household, brave-search]
```

`novak add` stays what it is: it adds a connection. `novak person add ushy` would
sit above it, creating the bank, asking for that person's keys, and recording
what belongs to them. Registry entries gain an `owner`, and an entry with no
owner is shared on purpose.

## Plan

0. **Now, no code.** In Open WebUI, restrict `hindsight-tmeuze` to the user
   `tmeuze` and `hindsight-ushy` to `ushy` with Access Control. The shared key
   is still underneath, but only that person can invoke that connection.
1. People directory and `novak person add`, plus `owner` on entries.
2. The gateway spike, then the choice.
3. Move Open WebUI onto the gateway (headers or token).
4. Per-person Home Assistant pipelines.
5. Close the Hindsight port to everything but the gateway. Satellites then reach
   household memory through the gateway with a household key, which is what
   makes closing the port safe for them (the earlier choice not to bind
   Hindsight to Tailscale only was to protect them, and this keeps that).

## Costs and risks

- The gateway holds every credential and sits in every request path: a single
  point of failure and the most valuable thing to compromise.
- A trusted header is only as good as the network around it.
- A pipeline per person is per device, not per login.
- More moving parts than one shared key, in exchange for the property you asked
  for.

## Does this need a reverse proxy?

The gateway is an application server and speaks MCP on its own port, so
satellites and a tailnet need no proxy in front of it. A proxy (Traefik, which
is being adopted anyway) becomes necessary if an OAuth client insists on an
HTTPS address for the resource, or if the gateway is ever exposed beyond the
tailnet. VERIFY whether Home Assistant's MCP OAuth flow accepts a plain-HTTP
tailnet address.

## Decisions taken

- A gateway is wanted, and the plan above is liked.
- A trusted header from Open WebUI is acceptable, but a Pocket ID token is
  preferred where a client can do it.
- Each person supplies their own key for services such as Tududi.
- Satellites go through the gateway with the household identity.

## Open questions

- Which Pocket ID version runs here, and does a client handle a Pocket ID API
  resource (VERIFY)?
- Should people paste their own keys into a form (console), or should an admin
  enter them?
