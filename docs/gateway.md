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

## Open WebUI: people, groups and models

Three things that look like one setting, and each can hide the others:

- **A person is a person once they sign in.** Their Open WebUI account appears the
  first time they use Continue with Inti, as a plain User. The gateway recognises
  them by the email Open WebUI has for them, which must match `people.yaml`.
- **Groups follow Inti, not Open WebUI.** `OWUI_OIDC_GROUP_MANAGEMENT` is on: at
  every sign-in Open WebUI removes the user from any of its groups whose name is
  not in their Inti `groups` claim, as long as the claim has at least one group.
  A group you build by hand in Open WebUI and fill by hand (for example "Users
  Novak") loses its members the next time they sign in, unless an Inti group has
  exactly that name and they belong to it. Name the Open WebUI group after an Inti
  group, or turn group management off and manage groups in Open WebUI only.
- **API keys are off until switched on.** A group's API Keys permission does
  nothing while `OWUI_ENABLE_API_KEYS` is false; set it true in `.env` and `novak up`.

If someone cannot see a shared model or the Workspace tab, the quickest check is
what the server itself thinks they may read (their groups, the model grants, and
their permissions); a stale browser session that predates the sharing is the other
usual cause, and a reload or sign-out and in fixes it.

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

## Approve and Deny buttons

A person whose `notify` is `{kind: ha, service: <name>}` gets a Home Assistant
notification with real **Approve** and **Deny** buttons (plus a Review link). `service`
may be a notify service (`mobile_app_pyrite`), a list of them, or a name from
`notify_groups` in `gateway.yaml` (`mgmt: [mobile_app_pyrite, mobile_app_aquarius]` sends
to both phones; whichever presses first decides, and a decision is final).

With `approval_helper` set the notification has no link: the review page is on the tailnet, so a tap on the body just opens the app. A button press is an event inside Home Assistant (`mobile_app_notification_action`). The
gateway cannot subscribe to events without an admin token, and it should not hold one, so
the press is passed on through a helper the gateway can read with its ordinary token:

1. Settings, Devices & services, Helpers, Create helper, **Text**. Name it
   `novak_approval`, maximum length 255 (entity `input_text.novak_approval`).
2. One automation: trigger **Event** `mobile_app_notification_action`; action
   **input_text.set_value** on that helper with the value `{{ trigger.event.data.action }}`.
   Add a condition so only Novak's presses count: the action starts with `NOVAK_`.
3. In `gateway.yaml`: `approval_helper: input_text.novak_approval`.

While a confirmation is waiting the gateway reads the helper every second and a half, and
acts only on an action carrying that approval's own token. Nothing polls when nothing waits.
A press takes a second or two to land. If the helper or automation is missing, the buttons
do nothing and the Review link still works.

### The approvals page

Buttons tell you less than the call itself, so a tap on the notification opens a page in
Home Assistant that shows what is being asked, with Approve and Deny. The gateway's token is
not an admin one and cannot publish a sensor state, but it can call services, so it fills a
second helper and the page reads that:

1. Helper: **Text**, name `novak_pending`, maximum length 255 (`input_text.novak_pending`).
2. Two scripts that write the decision to the approval helper, using the token in the pending one:
   `novak_approve` sets `input_text.novak_approval` to
   `NOVAK_APPROVE_{{ (states('input_text.novak_pending') | from_json).t }}`, and
   `novak_deny` the same with `NOVAK_DENY_`. Both do nothing when the pending helper is empty.
3. A dashboard (URL path `novak-approvals`, view `approvals`) with a Markdown card that shows
   `{{ (states('input_text.novak_pending') | from_json).who }}` and `.do`, and two button cards
   that run the scripts.
4. In `gateway.yaml`: `pending_helper: input_text.novak_pending` and
   `approval_page: /novak-approvals/approvals`.

With several requests waiting the page shows the newest; the notification buttons on each
phone still carry their own request's token, so none is lost.

## Narrowing a connection: `X-Novak-Scope`

A connection may send `X-Novak-Scope: <entry glob>[, ...]` to see only some of the entries
its person may already use (`ha-*` for the house alone). It only ever narrows: a scope cannot
add an entry the person is not allowed, and a call outside it is refused as an unknown tool.
Open WebUI uses it to give a "Home" preset a connection that offers just the house tools, since
a preset can switch on a whole connection but not individual tools.

## Approvals through Supernotify

`notify: {kind: supernotify, target: person.tyler_meuse}` (set with `novak person set NAME --supernotify
person.tyler_meuse`) sends the confirmation through [Supernotify](https://supernotify.rhizomatics.org.uk),
a Home Assistant integration. It reads each person's phones from Home Assistant's own people, so a new
phone is added in Home Assistant and nothing here changes. The call carries the Approve and Deny buttons
and the page a tap opens; the press comes back through the same automation and helper as before
([the buttons](#approve-and-deny-buttons)). `notify_default` takes a list of people, for anything that is
not one person's.

The call's shape was checked against a live install, because a wrong guess is not harmless: `actions`,
`delivery` and `dry_run` go at the **top level** of the call (inside `advanced` they are passed to the phone
as plain data), and `delivery.mobile_push.target` is a list. A simulated call (`dry_run: simulate`) sends
nothing and is not recorded.
## Lean tool lists: `X-Novak-Tools` and the house tools

A model can only use the tools that fit in its context. The models here have an 8,192-token window;
Home Assistant's own tools are about 21,000 tokens of definitions for the house alone and the gateway
offers 79 tools in all (about 34,000). A model given them loses the start of its prompt, so it ignores
its instructions and invents arguments.

- **`X-Novak-Tools: <glob>[, ...]`** limits one connection to the tools whose namespaced name
  (`<entry>__<tool>`) matches. Like the scope header it only narrows. The Open WebUI registry uses it
  to give the main connection about ten tools (about 2,400 tokens) and the Home connection two.
- **The house tools** (`house__house_state`, `house__lights_set`, about 450 tokens together) are built
  into the gateway and call Home Assistant's REST API directly (`house: {ha: 1, people: [tmeuze]}` in
  `gateway.yaml`; blank turns them off). `ha` is the instance id: the gateway reads `GATEWAY_HA_URL` (the
  address of that instance) and the secret `HA_1_ADMIN_API_TOKEN`, a long-lived token of a dedicated admin user (HA
  lets only an admin render the template that finds floors and areas). Only the listed people get them, the
  household never does, and the model never sees the token: the gateway calls two endpoints, one template
  and `light` services. They take floor and area names ("floor 2" matches areas labelled `L2`), resolve the
  lights themselves, and an unknown name returns an error that lists the real ones. They touch only lights,
  so nothing needs a confirmation. While no token is set, `entry: ha-mcp` (a person's own ha-mcp entry)
  still works as the older route.
- **The tasks snapshot** (`tasks__tasks_state`, about 100 tokens) is built in the same way on the person's
  own Tududi entry (the first entry whose name starts with `tududi`). It reads `list_tasks` for today and
  upcoming, drops the seventy-odd fields Tududi returns per task, and answers with a few lines: overdue,
  due today, the next seven days, later or undated, each task as `#id name | due | priority | status`.
  "Today" follows the gateway's `TZ` (set from `INGEST_TZ`). Completing or adding goes through the ordinary
  Tududi tools, which take the ids shown. It reads only, and people without a Tududi entry do not get it.

