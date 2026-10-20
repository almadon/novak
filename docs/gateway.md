# Gateway: one endpoint that knows who is asking

An optional service (decision #58, proposal in [identity.md](identity.md)).
Clients connect to the gateway instead of to each service. It works out which
person is calling, shows only that person's tools, adds that person's own
credentials on the way to each service, holds removals until they confirm,
and records who did what.

## What a person gets

- **Their own tools only.** Tool names carry the entry they belong to:
  `hindsight_tmeuze__recall`, `outline_everything__create_document`,
  `tududi_tui__create_task`. A person never sees, and cannot call, another
  person's entries, even by guessing a name.
- **Their own credentials downstream.** The service sees `tmeuze`'s key, so
  Outline and Tududi attribute the action to the right account. The caller
  never holds that key; the gateway does.
- **Adding is immediate, removing is confirmed.** Create, add and retain run at
  once. A delete, clear or similar is held, the person gets a notification with
  a link that shows exactly what will be removed, and the call waits for
  Approve or Deny (180 seconds by default). Approve runs it. Deny, or silence,
  does nothing. Updates and moves are allowed and logged; add `modify` to
  `confirm` in `gateway.yaml` to hold those too.
- **Accounting.** Every call is logged with person, how they were identified,
  entry, tool, kind of action, decision and outcome. Never the arguments or the
  results, only the argument names. `novak gateway audit [person]`.

The household (voice satellites) gets household entries and can read and add,
but removals are not even listed: there is nobody to confirm them.

## How a caller is identified

Strongest first.

1. **A Pocket ID token** whose audience is the gateway. The gateway checks the
   signature against Pocket ID's published keys and reads the person from the
   `preferred_username` claim, so identity is issued, not claimed. Turn it on
   with `GATEWAY_OIDC_ISSUER` (Pocket ID's address) and `GATEWAY_OIDC_AUDIENCE`
   (the API resource registered in Pocket ID for the gateway, normally
   `<gateway address>/mcp`). The gateway also serves
   `/.well-known/oauth-protected-resource` and answers 401 with a pointer to it,
   which is what an MCP client that can sign in uses to find Pocket ID.
   VERIFY against a real Pocket ID and a real client: tested here against a
   stand-in issuer only.
2. **A trusted client** (Open WebUI) sends its own key and names the user in
   the `X-Novak-User` header, matched against a person's `names` or `emails`.
   Only as safe as the network: nothing but that client may reach the gateway.
   Make the key with `novak gateway client open-webui`.
3. **A person's own key**, as `Authorization: Bearer <key>` or in the URL
   (`/mcp/k/<key>`) for clients that cannot send headers, such as a Home
   Assistant pipeline. `novak person add` and `novak person key` print it once.
   A person's key cannot be used to claim to be someone else.

Household: `/mcp/household` with the household key (or `/mcp/household/k/<key>` for clients that cannot send headers) (`novak gateway
household-key`), for satellites.

## Setting it up

1. `.env`: `GATEWAY_ENABLED=true`, `GATEWAY_BIND=<Tailscale IP>`,
   `GATEWAY_HA_TOKEN` (a Home Assistant token, for confirmations; use its own,
   not the drift or ingest token). Then `novak up`, which builds the image,
   writes `gateway.env` (only the credentials the directory names, mode 600) and
   starts the gateway.
2. Everyone is a person: `novak person add tmeuze` asks for their sign-in name,
   the email Open WebUI knows them by, a Ticker category (or Home Assistant
   notify service) for confirmations, and whether to create their Hindsight
   bank, then which existing entries are theirs. Credentials for each entry are
   set the usual way (`novak secret set TUDUDI_TUI_API_TOKEN`).
3. Household: `novak person share brave-search hindsight-household`, then
   `novak gateway household-key`.
4. Open WebUI: an admin registers one MCP connection to
   `http://gateway:8000/mcp` with the trusted-client key as a bearer token and a
   custom header `X-Novak-User` filled with the signed-in user's email (Open
   WebUI fills template tokens per request; VERIFY the exact token name on the
   running version). Remove the old per-service connections it replaces.
5. Home Assistant: one Assist pipeline per person whose agent's MCP server is
   `<gateway>/mcp/k/<their key>`. The household pipeline for satellites uses
   `/mcp/household`. Identity comes from which pipeline a device selects.

## Addresses that are secrets

Some endpoints carry their credential in the URL (HA-MCP's private path, for
instance). Such an entry names the variable instead of writing the address:
`url_env: HA_MCP_URL`. The variable is treated as a secret (`novak secret set
HA_MCP_URL`, shown masked, never printed by `novak registry`), is passed to the
gateway like any token, and the entry is skipped with a reason while it is unset.
`novak add mcp` asks whether the URL is secret.

## Which tools each entry offers

A model given every tool a service has does worse: it spends its context on
definitions and goes exploring. On the first live use through Open WebUI a
read-only question made a 14B model reach for `delete_knowledge_node` among 55
tools (the gateway held it and nothing was removed, which is the point of the
hold, but it should not have been offered the chance so readily). `tool_filters`
in `gateway.yaml` limits each kind of entry to the tools people use, by glob on
the entry name: `allow` keeps only the listed tools, `deny` removes more. A
filtered tool is not listed and cannot be called by name. Removal tools that
stay on the list still need confirmation. The shipped defaults give Hindsight
16 tools and Outline 11; Tududi is unfiltered until its tool list is seen.

## Entries and people

An entry (in `mcp-servers.yaml`) holds one credential, so it belongs to one
person or to the household, never two people. `novak person attach` refuses to
give one entry to two people; `check` reports it. Tududi's sharing between
accounts happens inside Tududi, so each person just has their own entry.

## Commands

| | |
|---|---|
| `novak person add NAME` | create a person, optionally their memory bank, and a gateway key |
| `novak person list` | who exists and what is theirs |
| `novak person attach/detach NAME ENTRY...` | their entries |
| `novak person share/unshare ENTRY...` | household entries |
| `novak person key NAME` | new key (the old one stops working) |
| `novak gateway client NAME` | a trusted client key |
| `novak gateway household-key` | the satellites' key |
| `novak gateway status / check / audit [person]` | health, directory problems, accounting |

## Limits, honestly

- **The gateway holds every credential and sits in every request path.** It is
  the most valuable thing here to compromise and a single point of failure.
- **A held removal blocks the calling request** while it waits. A client with a
  short timeout may give up first; the approval then does nothing (it expires).
- **Tool classification is by name.** `tool_overrides` in `gateway.yaml` fixes a
  misleading one. An unknown name counts as an update: allowed and logged.
- **Hindsight's own port is still open** until step 5 of the plan in identity.md
  (close it to everything but the gateway). Until then a person who knows the
  shared key can still reach any bank directly.
- **Not built:** per-person self-service for pasting a key (an admin enters it),
  streaming responses (replies are plain JSON), and resources and prompts
  (only tools are proxied).
