# Decisions

Why things are the way they are. Each entry says what was decided, why, what it
cost, and what would make it worth revisiting.

Written in plain language on purpose. If a sentence here needs a glossary, it's
a bad sentence — rewrite it.

All entries dated 2026-08-16 unless noted.

---

## 1. The hub is a set of services, not an app

Every client — Open WebUI, Home Assistant, the console, anything later — talks
to the same inference server and the same tools. No single program owns the
system.

**Cost:** more moving parts than one all-in-one app.
**Why anyway:** if any one piece dies or gets abandoned, the rest still works.
This has already paid off twice (see #2 and #3).

## 2. Not adopting Tater

Tater is a capable all-in-one assistant platform: it runs models, voice, memory,
and talks to Home Assistant. Rejected because it wants to *be* the system —
Home Assistant becomes a plugin of Tater rather than an equal.

Two of its supporting repos were retired within about three months of each
other while we were evaluating it, which is a lot of churn to build on.

**What it genuinely has that we don't:** firmware for purpose-built voice
satellites like the Sat1. That firmware reports to Tater's own backend, so it
can't simply be borrowed.
**Revisit if:** you want the satellite hardware more than you want the
architecture, or Tater's pace of change settles down.

## 3. Memory: Hindsight, after two false starts

The stack was originally built on **OpenMemory**. Upstream deprecated and shut
it down.

Its replacement, **Mem0**, got as far as being written into the compose file
before two problems surfaced. It publishes no image for the current server —
their own compose builds from source and needs an init script, migrations and a
bootstrap that prints an unrecoverable API key. And it has no MCP interface, so
it needed ~400 lines of first-party shim to expose it and to stop the model
choosing whose memories to read.

**Hindsight** does both natively. It ships an image with Postgres embedded, and
its MCP server scopes each connection to one bank *by URL*, with no bank
parameter on the tools. The shim was deleted.

**Cost:** a third backend change before anything ran. Some churn was
self-inflicted — an image name was invented rather than verified, and a README
search was mistaken for evidence of no MCP support.
**Why anyway:** it is less code, less deployment, and the security property is
upstream's rather than ours to maintain. See
[how-memory-works.md](how-memory-works.md).

## 4. Memory engines we looked at and passed on

- **Graphiti** (from the Zep team) — better at facts that change over time
  ("Alice *used to* work at X"). Passed for now: it wants a graph database, and
  it calls the language model several times for every memory it stores. On a
  24GB Mac mini that's also answering voice in 1–2 seconds, that competes for
  the same hardware.
  **Revisit if:** tracking how facts change over time becomes something you
  actually want. Pair it with Kuzu or FalkorDB, not Neo4j.
- **Letta** — mature, but it's an agent framework that wants to run the
  conversation itself. That's the same shape we rejected in #2.
- **keep** — MCP-native and actively developed, but it has no concept of
  users at all, and its multi-user option is a hosted cloud service. It's a
  good tool for *agent* memory; it just can't separate people.

- **supermemory** — MIT and popular, but its namespace is a `containerTag`
  **passed as a parameter**, which is the caller-supplies-identity pattern this
  design rejects. No published image either, and the hosted platform runs on
  Cloudflare, ruled out elsewhere in this fleet on privacy grounds.
- **Mem0** — see #3. Fine software; the deployment story and the missing MCP
  interface were the problem, not the memory model.

Note: most "best memory framework" comparison articles are marketing from
companies selling one of the options — including at least one published by the
company behind the backend eventually chosen. Their benchmark numbers were not
used; the decision rested on the identity model, the deployment shape, and the
licence.

## 5. There is a web console, and that's allowed

The README says "no custom web frontend." The full sentence also says: *build
UI only for things chat can't express, and build it as a view over these same
services.*

Browsing memories, editing a persona, and managing plugins are things you can't
sensibly do by chatting. So the console exists — but it owns nothing important.
If it vanished, no data would be lost.

## 6. The console has no control over Docker

The console can add and remove MCP servers. It does this by writing a file
(`registry/mcp-servers.yaml`); a separate script on the host reads that
file and starts containers.

**Why not let the console run Docker directly:** anything that can create a
container can create one that has full access to the machine. There's no way to
allow "create a container" safely. So the web-facing part simply never gets
that power.

**What this buys:** if someone breaks into the console, they can write a YAML
file. That's it. And every change is a file in git, so you can see what changed
and undo it.

## 7. Staying on OrbStack (not Apple's container tool, not Podman)

Apple's `container` reached 1.0 in June 2026 and gives each container its own
small virtual machine — better separation than OrbStack, which uses one shared
VM for everything.

Passed because:
- It has no `docker compose` support, and this whole stack is compose.
- Its memory handling doesn't reliably give RAM back to the host. On a 24GB
  machine that's also running language models, that's a real problem.
- The extra separation was mostly answering a risk we removed in #6 anyway.

Podman on macOS also runs a VM, so switching there changes a lot and gains
little.
**Revisit if:** Apple's tool gains compose support and the memory behaviour
improves.

## 8. Voice shares one memory — now for only one reason

Originally this had two causes. One has gone away.

**Gone:** Home Assistant's MCP client can only authenticate with OAuth — no
tokens, no custom headers — which made per-person scoping impossible when the
backend needed a bearer token. Hindsight puts the bank in the URL path, so HA
is correctly scoped with no header at all.

**Remains:** a voice satellite cannot tell who is speaking.

So voice points at a shared `household` bank, and personal banks are never
registered in Home Assistant. That is now a statement about microphones rather
than about software.

**Cost:** none that is fixable in this layer.
**Revisit if:** speaker identification becomes trustworthy — but see #9, which
is not as simple as it sounds.

## 9. Speaker identification: useful, but not for deciding who sees what

`wyoming-voice-match` is the best of the options examined — good model, fits our
existing voice setup, and it cleans up audio by removing other voices before
transcription. Worth adopting for that alone.

**But it must not decide whose memories get read.** It identifies a speaker by
adding a tag to the transcript text, like `[john] what's the weather`. That tag
lives inside the words sent to the model, which means anyone who says the right
words — or any document the model reads containing that text — can claim to be
someone else. It tells you who's *probably* speaking; it doesn't prove it.

Also: it adds 200–500ms on a CPU, and it's least accurate on short phrases,
which is what voice commands are.

**Safe path if you want per-person voice memory later:** strip the tag and pick
the memory connection *before* the model sees anything, so the model never gets
a say in whose data it's reading.

### Also evaluated: EuleMitKeule/speaker-recognition

A later candidate, and better built on the point that sank the first. It is a
custom HA integration with a REST API and neural voice embeddings
(Resemblyzer), and it reports a **confidence score** rather than editing the
transcript. That satisfies the safe path above: the identity arrives as
structured data outside the words, so no document and no clever phrasing can
claim to be someone else.

**It changes the delivery problem and not the underlying one.** A voice
embedding is evidence, not proof. Confidence around 0.95 means roughly one turn
in twenty is wrong, and applied to memory routing a wrong turn is a disclosure,
not an annoyance. The earlier cautions also stand: 200-500ms against a 1-2s
budget, and worst accuracy on short utterances, which is exactly what voice
commands are. Its README has no limitations section at all, which is not
reassuring in something that makes identity claims.

Health at time of writing: 48 stars, MIT, last commit 2026-05-01.

**So: adopt it for personalization, never for authorization.** Greeting by
name, preferring someone's music, choosing a voice — being wrong there is
merely irritating. Selecting a memory bank — no.

And note where it is actually needed. Decision 21 establishes that identity
comes from the channel: a personal phone or browser session already answers
"who is this" with something signed. **Speaker recognition earns its place only
on a shared satellite** — the one channel authentication cannot reach — and
there it may personalise while the bank stays household. It adds warmth exactly
where proof is impossible, and is redundant everywhere proof exists.

## 10. Powerful integrations are allowed, but must be turned on deliberately

`ha-mcp` gives a model 88+ tools over Home Assistant, including editing config
files and creating automations. That's genuinely useful and genuinely
dangerous — especially anywhere the model reads outside content like email or
calendar entries, which could contain instructions aimed at it.

Rather than ban things like this, the registry has a risk level. Anything above
`standard` won't start until someone writes down what it can do, who accepted
that, and when. Turning it off again needs no ceremony.

The principle: your call, but make it on purpose, and leave a note for
future-you.

## 11. Where things run

The stack is spread across machines, not all on the mini.

- **Must be on the mini:** oMLX (needs Apple's GPU directly).
- **Should be near oMLX:** memory — every memory written triggers model calls.
- **Already elsewhere:** Open WebUI, on a VPS.
- **Chosen: mini** — the console, so memory reads are local.

**Cost of that last one:** login uses Pocket ID, which runs on a VPS. If the
internet is down, you can't sign in to a console that is otherwise entirely
local. Existing sessions last 8 hours, so brief outages don't lock you out.

Also worth knowing: with the model at home and Open WebUI on a VPS, chat stops
working if the link between them drops. Voice keeps working, because it's all
local. Voice is the more reliable interface, not the less.

## 12. The console lives in its own repository

The web console was extracted to a separate repo, `novak-konzol`. The registry
it edits and the reconciler that applies that registry **stayed here**.

That division is the point. The registry describes what *this* stack runs, so
it belongs to this stack; the reconciler is the only thing with power over
containers, so it stays as far from the web app as possible. What moved out is
just the user interface.

The entire interface between the two repos is one bind-mounted directory. The
console writes a file. Something else, with no network exposure, acts on it.

**The console is optional.** Editing `registry/mcp-servers.yaml` by hand and
running `reconciler/reconcile.py` is a fully supported path — the stack has no
dependency on the console existing, and the deploy checklist treats it as a
skippable section.

**Cost:** two repos to keep in step, and the console is now consumed as a
published image rather than built in place, which means its CI has to work
before it can be deployed.
**Why anyway:** it's a Next.js app with a different toolchain, different CI, and
a different release rhythm from a pile of compose files — and making the
boundary a repository boundary means it can't quietly grow tendrils into the
stack it's supposed to merely view.

## 13. Three repos: core, integrations, console

Extending #12. The split is now:

| Repo | Holds | Why there |
|---|---|---|
| `novak` (srz) | compose, docs, registry, reconciler | The orchestration and the decisions |
| `novak-integracije` | MCP servers and adapters | Capabilities, replaceable individually |
| `novak-konzol` | the web console | A client, and optional |

The dividing line is **what a given install runs** versus **what exists to be
run**. The registry says "this machine runs memory and vikunja at these risk
levels" — that's per-deployment, so it stays in core. The integrations repo is
the catalogue of things that *could* be run. Those are different questions and
they change at different rates.

The reconciler stays in core because it's the only component with power over
containers, and it should sit as far as possible from anything a third party
might contribute to.

**Cost:** three repos, and integrations are now consumed as published images —
so an integration's CI has to work before you can deploy it.
**Why anyway:** "bring your own engine, hardware, integration" only works if
adding one doesn't mean editing the core. And a store needs a shelf.

## 14. MCP servers are defined in the registry, not in compose

Consequence of #13 that's worth stating separately, because it closed a real
piece of debt: `docker-compose.yml` no longer contains any MCP server. They are
registry entries, rendered by the reconciler into a second compose file that
`scripts/up.sh` applies alongside the first.

Previously both files described the same servers, and the docs carried a
warning not to enable both or the ports would collide. That warning is gone
because the duplication is gone.

`up.sh` now runs the reconciler as a **hard gate**: if a registry entry is
enabled at `elevated` or `dangerous` without a recorded acceptance, the whole
start fails rather than quietly skipping that one service.

## 15. Internet exposure is decided per service, and the home network takes
## nothing inbound

Not everything gets the same treatment, and the split follows what each piece
was *built* to withstand.

| Service | Where | Reachable from | Why |
|---|---|---|---|
| Reverse proxy, Open WebUI | VPS (Constant) | the internet | Designed to face it: accounts, sessions, TLS at the proxy |
| oMLX | Mac | Tailscale/LAN only | An inference API with no rate limiting; assumes friendly callers |
| Hindsight | Mac | Tailscale/LAN only | Holds everyone's memories; open unless the tenant API key is set |
| Konzol | Mac | Tailscale/LAN only | Can reconfigure the stack |
| Wyoming voice | Mac | LAN only | Talks to satellites on the local network |

**The home network forwards no ports at all.** The VPS reaches the Mac over
Tailscale. So the chat interface is usable from anywhere, while nothing at home
accepts a connection from the internet.

The useful way to think about it: *being on the internet is a property a
service has to earn by being designed for it,* not a default you grant because
it would be convenient. Open WebUI has accounts and sessions and expects
strangers to knock. oMLX does not.

**Cost:** the chat interface stops working if the link between the VPS and home
drops — the model is at home. Voice keeps working, because voice is entirely
local. Voice is the more reliable interface, not the less.

**Revisit if:** something new needs public reach. That's a per-service decision
with the same shape as a risk acceptance in the registry — write down what it
is, why it needs to face the internet, and what's in front of it.

## 16. TLS on the local network, using the proxy that already exists

Separate question from #15. That one was about who can reach things; this is
about whether traffic can be read in transit.

First, correcting a common assumption: **Tailscale traffic was already
encrypted.** It's WireGuard underneath, so tailnet hops were never sniffable.
The actual gap was the **LAN** — Home Assistant talking to memory, a browser
reaching the console, anything hitting a published port by IP.

**Novak does not run its own reverse proxy.** There is already an internal
proxy on another host; adding a second inside this stack would duplicate
infrastructure for no gain. [`proxy/`](proxy.md) holds config to add
to the existing one, in both Caddy and Traefik form, since a move to Traefik is
planned.

```
   browser / HA ──TLS──▶ existing internal proxy ──Tailscale──▶ the Mac
```

Both hops encrypted, nothing new deployed. The last hop is WireGuard rather
than TLS, which is not a weaker guarantee.

Certificates use a **DNS-01** challenge — it proves domain ownership by writing
a DNS record instead of accepting an inbound connection, which is the only way
to get real certificates for names that resolve to a private address behind no
port forwarding.

**Performance cost:** negligible. TLS 1.3 adds one round trip at connection
setup, and the symmetric crypto is hardware-accelerated. Not measurable against
token streaming.

**What stays plaintext:** the Wyoming voice services. Wyoming is a TCP protocol
and the ESPHome satellites can't do TLS to a hostname; proxying them would
break them. So voice audio is readable by anything on the local network. That
is the same network the microphones already sit on, but it is a real gap and
nothing here closes it.

**The other loose end:** for the proxy on another host to reach these services,
they bind on the tailnet rather than localhost — so anything on the tailnet can
reach them directly and skip the TLS. Tailscale ACLs are the answer, not
firewall rules on the Mac.

## 17. oMLX models and profiles come from files, not the admin API

[`docs/omlx-settings.md`](omlx-settings.md) is a table of model names,
temperatures, idle TTLs and profile names that a person retypes into a web
admin panel. Nothing checks the result afterwards. A mistyped temperature or a
profile that never got created looks exactly like a working install until
something answers badly, which is the same silent-failure shape as the
`OMLX_PORT` mismatch that had chat and memory pointed at a dead port while
every container reported healthy.

So it should be applied by machine. The question is through which door.

**The admin API is the obvious door, and it is the wrong one.** oMLX exposes a
complete one — `POST /admin/api/hf/download` for models, `POST`/`PUT` on
`/admin/api/models/{id}/profiles` for profiles, with task polling and retry. It
is genuinely capable. But it sits behind its own admin session
(`POST /admin/api/login`), separate from `OMLX_API_KEY`. Using it means a new
secret in the Keychain and provisioning code that logs in and holds a session.

That breaks something deliberate. The reconciler is built so it never sees a
secret *value* — the registry carries variable **names**, and compose resolves
them at up-time (#14). Handing the same component an admin password to hold
would undo the one property that makes it safe to point at a file the console
can write. Not worth it for a config-application convenience.

**Files are the other door, and oMLX already stores everything there.** Three
JSON files under `~/.omlx`, written atomically (temp file + rename):

```
model_settings.json    per-model — idle TTL, default/pinned, display name
model_profiles.json    profiles, keyed by model id
global_templates.json  profile templates, model-independent
```

Templates accept only the *universal* fields — sampling, thinking, context —
and are not tied to a model id. That is what makes this work at bootstrap
time: **the templates can be written before a single model exists**, which the
API route cannot do, since it needs a running server and a downloaded model to
attach to. Per-model profiles still need the model present, so they come later.

**Cost:** the on-disk format is undocumented and version-coupled to a
third-party app. `settings.md` already warns that setting names drift between
oMLX versions. Anything applying these files must validate against the field
list it knows and **fail loudly** — a profile that quietly did not take is
worse than one that refused.

**The other cost:** oMLX holds this state in memory and writes it atomically,
so files written underneath a running server get clobbered on its next save.
Writes happen with the server stopped — `omlx stop` and `omlx start` need no
admin auth, unlike everything above.

### What this settles, and against the guess

**oMLX profiles do not carry a system prompt.** The field list is sampling,
thinking, and cache tuning — `temperature`, `top_p`, `enable_thinking`,
`thinking_budget_tokens`, the DFlash and TurboQuant knobs — and nothing else.
There is no persona field, so the "set it once in the profile and every client
inherits it" option in `settings.md` does not exist.

The documented fallback stands: [`prompts/`](../prompts/) is the master copy and
each client gets its own copy — Open WebUI's model preset, Home Assistant's
agent prompt field. They will drift; that is now a known maintenance cost
rather than a surprise. This closes the `VERIFY` that has been open since the
repo was written off-host.

Idle TTL is not a profile field either — `ttl_seconds` is explicitly excluded
from both profiles and templates, so it belongs in `model_settings.json` per
model. `settings.md` lists it per model, which was right.

### Still open

Downloading the models themselves. `model.model_dirs` points at
`~/.omlx/models`, so `hf download` straight into that directory may be all it
takes and would avoid the admin API for that too — **VERIFY** that oMLX
discovers models placed there rather than requiring its own downloader.

**Built** as [`reconciler/omlx_apply.py`](../reconciler/omlx_apply.py), run by
`novak omlx apply` and, non-fatally, by `up.sh`. Two things learned building it:

The accepted field list is read out of the installed oMLX rather than hardcoded,
so it tracks the version actually running and the version-coupling above becomes
self-correcting. An unrecognised field aborts the run.

Success is confirmed by observation — after restarting, the exposed profiles
must appear in `/v1/models` or the run fails. That matters because the
`model_id` key had to be inferred, and a wrong guess would otherwise have
written a file that oMLX quietly ignored.

Also settled while building it: a profile must be marked `expose_as_model` or no
client can select it, and profiles are exposed as `<model_id>:<api_name>` —
`Qwen3-14B-4bit:chat`, not `chat`. `docs/omlx-settings.md` said otherwise and is
corrected.

## 18. Prompts are pushed to clients, because no client will pull them

Decision 17 established that the persona cannot live in oMLX. The obvious next
hope is that it lives in one place anyway and the clients read it — a file, or
better, this repo. They will not.

**Open WebUI** keeps system prompts in its own database, set through Workspace
→ Models or per-model parameters. **Home Assistant** keeps the conversation
agent's prompt in its config entry, set through the integration's options UI.
Neither has a "read this from a path" or "sync from git" option. There is no
version of this where the clients pull.

So the direction is fixed: **something has to push.** The only real question is
whether that something is a person or a program, and the whole point of
[`registry/`](../registry/mcp-servers.yaml) is that it should be a program.

### The shape

`prompts/` in git is the source. An apply step reads it and writes each client
through its own API — Open WebUI's model preset, Home Assistant's agent config.
Same shape as decision 17: declarative input, dumb applier, fail loudly.

Running it on change is what makes it continuous rather than a chore. A commit
that touches `prompts/` triggers the apply, and `novak status` reports drift
between what the repo says and what each client currently holds — so a persona
edited by hand in a web UI shows up as a difference rather than a mystery.

That drift check is the more valuable half. Pushing on commit keeps the copies
current; the status check is what catches someone editing the copy instead of
the master, which is the failure that actually happens.

### The cost, stated plainly

**This is weaker than the registry.** MCP servers end up in exactly one place —
compose — so the file *is* the state and drift is not possible. Prompts end up
as copies in databases that can be edited in place. Convention plus a drift
check is a real guarantee, but it is not the same guarantee, and it should not
be described as if it were.

**It matters more than it looks.** [security.md](security.md) leans on the
persona to enforce behaviour: never ask for credentials, treat retrieved
content as data rather than instruction, confirm before acting. With per-client
copies, that enforcement is only as strong as the least-well-configured client.
A client whose persona silently reverted is a client with weaker safety
behaviour, and nothing about it will look broken.

### Why not a proxy in front of oMLX

The alternative is middleware that injects the persona into every request, so
there is exactly one copy and clients need no persona config at all. It is a
real option and it solves the drift problem properly.

**Superseded by decision 21.** The conclusion below was scoped to a client
count — two clients, both with a persona field — rather than to a principle,
and two of its three grounds do not survive scrutiny. Kept because the
reasoning is instructive and because it names the condition that eventually
triggered the change.

It is rejected for now, on three grounds:

**It rebuilds what was just deleted.** The Mem0 shim (see the memory section in
[architecture.md](architecture.md)) was ~400 lines of first-party code in the
request path, removed when Hindsight made it unnecessary. Putting a new
first-party service back into that path for prompt templating is a worse trade
than the one just unwound.

**It lands in the latency budget.** A voice turn is ~1-2s end to end across
Whisper, inference and Piper. A proxy in front of oMLX taxes every turn,
including the ones that need no persona work at all.

**It widens the blast radius.** Open WebUI reaches oMLX from the VPS over
Tailscale. A component in that path fails *all* inference everywhere, rather
than one client having a stale persona.

Provisioning-time consistency is strictly cheaper and does not foreclose this.
If per-user context or request-time policy ever needs to be injected — things
static config genuinely cannot express — that is the moment to revisit, as its
own decision, with the shim's deletion as the argument to beat.

That moment arrived, and the trigger was the one named above. See decision 21,
which also corrects the latency figure: a router on this machine costs well
under a millisecond against generations measured in seconds, so "it lands in
the latency budget" was wrong about the magnitude, not just the balance.

### VERIFY before building

Neither client's API was exercised. Open WebUI 0.11.0 here still has
`onboarding: true`, so no admin account and no API token exists yet, and Home
Assistant does not run on this machine at all. Confirm the actual endpoint for
setting a model's system prompt in each before writing an applier against it.

## 19. Home Assistant's conversation agent: Custom Conversation

Home Assistant's own OpenAI integration still refuses a custom base URL
([core#137087](https://github.com/home-assistant/core/issues/137087)), so
talking to oMLX needs a custom component. There are three plausible ones and
the choice is not simply the most popular.

Measured 2026-08-19:

| | Stars | Last commit |
|---|---|---|
| `michelle-avery/openai-compatible-conversation` — what this repo used to say | 38 | 2025-09-09 |
| `jekalmin/extended_openai_conversation` | 1,428 | 2026-05-17 |
| `michelle-avery/custom-conversation` | 93 | 2026-08-05 |

**The old recommendation is disclaimed by its own author**, who writes: *"I
personally cannot support this, as I don't actually use this integration, which
makes ensuring its quality challenging."* They are looking for a maintainer and
point at Custom Conversation, which is theirs and which they do use. Eleven
months without a commit on a fork of a fast-moving upstream is the real problem;
the disclaimer just makes it explicit.

### Why not the popular one

Extended OpenAI Conversation has thirty-seven times the stars, and it would
work. It is not chosen because **it is a different architecture, not a
different base-URL field.** It brings its own function-calling system for
device control, replacing Home Assistant's intent handling.

This stack is deliberately arranged the other way: the conversation agent
handles *language*, and tools arrive through HA's MCP client — the same
endpoints every other client uses (#14, and the memory section in
[architecture.md](architecture.md)). Moving device control into the agent's
own function calling would mean voice tools stop being the shared MCP surface
and become a per-client thing again.

It also costs latency where there is none to spare. Every function definition
sits in the context of every spoken turn, against a 1–2s budget. The registry
already keeps Tududi off the voice pipeline for exactly this reason, at 59
tools; adopting an agent whose model of the world *is* tool definitions works
against that.

**When it is the right answer:** if you decide you want the model driving
devices directly rather than HA's intents doing it. That is a real position,
and this decision is not an argument that it is wrong — only that it is a
change of design rather than a swap of component, and should be taken as one.

### The cost of what was chosen

Custom Conversation has 93 stars. It is small, and being actively maintained by
one person who uses it is a better guarantee than 1,428 stars on code nobody has
touched in three months — but it is still one person.

It reaches the endpoint **through LiteLLM**, so there is a translation layer
between HA and oMLX that neither project tests against the other. Its own docs
warn that *"supposedly 'OpenAI-compatible' APIs are sometimes not fully
compatible."* oMLX serves both `/v1/chat/completions` and `/v1/responses`, so
the surface is there; that is not the same as the pairing having been exercised,
and the voice path should be tested end to end before it is trusted.

### A thing worth knowing either way

The maintenance note blames HA's native agent diverging by adopting the
**Responses API**, "which many OpenAI-compatible services don't support". oMLX
does support it. So that particular divergence is not a problem here — which is
an argument for tracking a component that follows current HA, and against the
frozen fork specifically.

## 20. Home Assistant reaches Hindsight through a header-injecting proxy

Two components that both speak MCP cannot authenticate to each other.

**Home Assistant's MCP client speaks OAuth only.** Its config flow asks for a
Client ID and Secret from Application Credentials, and offers no field for a
bearer token or a custom header.

**Hindsight authenticates with a static API key** in an `Authorization` header.
Its shipped tenant extensions are `Default`, `ApiKey` and `Supabase` — none of
them OAuth. The key is accepted in a header and nowhere else; as a query
parameter it is a 401.

There is no overlap, so pointing HA at the bank URL fails:

```
httpx.HTTPStatusError: Client error '401 Unauthorized'
  for url 'http://<mac>:8888/mcp/household/'
```

This invalidated something the repo asserted. The registry entry said Home
Assistant *could* use this endpoint because the bank sits in the path and needs
no custom header. That was true of bank *selection* and wrong about
authentication — one header problem was solved and read as though both were.

### What was chosen

The proxy holds the credential and adds it per request. HA talks to a route
that asks nothing of it; Hindsight still refuses anything arriving without the
key. Config for both Caddy and Traefik is in [proxy.md](proxy.md).

**This is the first concrete reason to run a proxy on this network.** #16 added
one for TLS, which was optional given the tailnet is already WireGuard. This is
not optional: without it, voice has no memory.

**Cost, stated plainly.** The route converts "holds the key" into "can reach
this hostname", so it must be restricted to Home Assistant's address — a
source-IP rule, not an afterthought. And the credential now lives on the proxy
host as well as in the Mac's Keychain: a second copy, and a second place to
rotate it.

### What was rejected

**Turning Hindsight's tenant auth off.** It would work immediately and leave
the MCP endpoint open to everything that can reach the port — every bank, read
and write, no credential. `docker-compose.yml` already carries that warning in
capitals. Trading all authentication for one client's convenience is the wrong
shape of fix.

**Writing an OAuth tenant extension for Hindsight.** The clean answer, and real
work in someone else's codebase, on an interface that would then need
maintaining against upstream.

**Waiting for HA's MCP client to accept a token.** Also a clean answer, also
not in our hands. Worth watching: if it lands, this proxy route becomes
unnecessary and should be removed rather than kept out of habit.

### The general shape

Worth noticing because it will recur: two things that both "support MCP" still
have to agree on **authentication**, and MCP does not settle that. Protocol
compatibility is not integration compatibility. The registry's `auth:` field
records which credential an endpoint needs precisely because nothing injects it
automatically — every client has to be capable of presenting it, and this one
is not.

## 21. An inference routing layer, because uniformity cannot be a client setting

Supersedes the second half of #18.

The project's claim is that memory, knowledge and behaviour belong to *you*
rather than to whichever program you happen to be typing into. Memory already
works that way: Hindsight holds it, the bank is in the URL, and no client can
name someone else's. Persona does not. It exists as a copy inside every client,
maintained by hand, drifting quietly.

That is not a tidiness complaint. **Per-client configuration cannot express what
this project is for**, and no amount of care fixes it:

- Open WebUI has **one** system prompt per model preset, shared by every user of
  it. "Isolated, multi-user" is unreachable from there.
- Every new client is another copy to write and another chance to differ.
- Nothing can vary by *who is asking*, because nothing in the path knows.

A layer that sees the request is the only thing that can. #18 said as much and
then rejected it on cost, which was right for two clients and wrong as a
principle — an architecture is what it must become, not what is cheapest at N=2.

### The shape

An OpenAI-compatible router in front of oMLX. Clients point at it instead, and
carry no persona of their own.

```
Open WebUI ─┐
            ├─▶ router ──▶ oMLX
Home Assist ─┘   (persona, identity, policy)
```

**LiteLLM is the vehicle.** Streaming, retries and OpenAI compatibility are
solved problems and not worth re-solving; the injection itself is a small
`async_pre_call_hook`. That is first-party code in the request path again, which
#18 was right to weigh — but a hook inside a maintained gateway is a very
different object from the ~400-line shim that was deleted, and unlike that shim
it does something no backend does.

**`prompts/` stays the master copy.** It is pushed to one place instead of N,
which is what makes #18's drift problem tractable rather than perpetual.

### Identity, and why it is the interesting part

Open WebUI can forward the authenticated user with
`ENABLE_FORWARD_USER_INFO_HEADERS`: `X-OpenWebUI-User-Id`, `-Email`, `-Name`,
`-Role`, `-Jwt`.

With a verified identity in the request, the household/personal split stops
being "which URL did this client happen to register" and becomes a routing
decision. That finishes *memory that follows you* rather than approximating it,
and it is the capability that justifies the layer — persona uniformity alone
would not.

**Trust the JWT, not the header.** Anything that can reach the router could
forge `X-OpenWebUI-User-Id`. The router validates `X-OpenWebUI-User-Jwt` and the
route stays source-restricted, exactly as in #20. A plain header is a claim; a
signature is evidence. Getting this wrong would hand one person another's
memories, which is the failure this whole architecture exists to prevent.

### Identity comes from the channel, not the modality

An earlier draft of this said Home Assistant could not participate in the
multi-user half, because "a microphone cannot tell who is speaking". That is
true of a **shared satellite** and false of voice in general, and the difference
matters: roughly half the voice surface is authenticated as well as Open WebUI
is, by the same means — a login plus a device someone owns.

Home Assistant hands the conversation agent more than its public API docs
suggest. `ConversationInput` carries:

```python
context: Context        # context.user_id — the authenticated HA user
device_id: str | None
satellite_id: str | None
```

So:

| Channel | Identity | Scope |
|---|---|---|
| Companion app on a personal phone | authenticated `context.user_id` | personal |
| Assist in a browser session | authenticated `context.user_id` | personal |
| Siri / Shortcuts via HA's API | personal long-lived token | personal |
| A speaker in the kitchen | nobody — anyone in the room | **household** |

**`satellite_id` is the discriminator**, and it is a field rather than an
inference. A request carrying one arrived through shared hardware; one carrying
a `user_id` and no satellite came from an authenticated personal session.

The rule, stated so that it fails safe:

> Scope to a personal bank only when `context.user_id` is present **and** no
> shared `satellite_id` is involved. Otherwise, household.

A missing field yields household rather than a personal bank, so the failure
mode degrades toward less disclosure rather than more. That direction is not
incidental — it is the whole reason to write the rule this way round.

### Costs, stated plainly

**It is a true single point of failure.** #20 already accepted a proxy in the
path, but that one only breaks memory. This breaks *all* inference, text and
voice. It must be treated as infrastructure — on the mini beside oMLX, not
across a WAN link, and watched.

**It is another place the persona lives.** One place instead of many is the
gain, but it is not zero, and it needs the same drift check as anything else.

### Order of work

The drift check first, then the router. Not the reverse: the check is what
tells you whether the layer is delivering the uniformity it was built for, and
building the layer first means trusting an unverified claim about the thing you
built to fix verification.

## 22. The portal: Novak's first self-run reverse proxy, scoped to one page

Konzol can't structurally become a section of Open WebUI. Checked directly:
Open WebUI's extension system (Tools, Pipes, Filters, Actions, Events) hooks
chat behaviour and system events, not UI navigation, and there is no
first-party mechanism to register a new admin-panel page. The only way to
make it "part of Open WebUI" would be forking Open WebUI's own frontend
source, which is a materially larger and differently-shaped commitment than
anything else in this stack: a maintained fork against a fast-moving
upstream, for a much bigger surface than Konzol's own codebase, under a
licence (`credits.md`'s Open WebUI `VERIFY`) that has already changed once.

What was actually wanted was closer to two things: a single browser tab for
the household's day-to-day surfaces, and one Pocket ID group governing who
can reach the admin ones. The second is already solved natively (see the
`feat/owui-oauth-group-admin` change: `admins.novak` now grants Open WebUI's
own admin role and group, no new code). This decision is about the first.

### What was chosen

A static page (`portal/index.html`) with a tab per app, iframing Open WebUI
and Konzol at their own existing ports rather than proxying them. Caddy
serves the page and gates it with TinyAuth's forward-auth against Pocket
ID's `admins.novak` group — the same group everywhere else now uses. Full
design and what was verified versus assumed: [proxy.md](proxy.md#portal-a-single-page-over-open-webui-and-konzol).

**This is Novak's first reverse proxy that Novak itself runs.** Every prior
mention of a proxy (#16, #20) was something running on another host,
fronting Novak's ports from outside. `docs/proxy.md` said as plainly as
anything in this repo says something: "Novak does not run a reverse proxy."
That line is now qualified, not deleted — the portal's Caddy instance fronts
exactly one static page, nothing else in the stack, and every other service
keeps reaching the network exactly as it did before this.

**Cost, stated plainly.** A new service, a new forward-auth service behind
it, a fourth Pocket ID OIDC client, and a page that has to be kept honest
about which apps it lists as more get added. TinyAuth is AGPL-3.0 — run
unmodified, which is the low-risk case (`credits.md`), but a real dependency
this project now carries and has to keep patched. And `TINYAUTH_APPURL`
must be a real hostname, never the Tailscale IP `novak ports` otherwise
treats as an equally valid way to reach everything else — confirmed
directly, not assumed, and it is the one place in this stack where that IP
stops working.

### What was rejected

**Reverse-proxying Open WebUI under a subpath**, so the portal could be the
only origin involved. Tested directly against the running container before
building anything else on top of the assumption: Open WebUI ships absolute
asset paths and breaks under a subpath without rewriting this setup does
not do. Each app keeps its own port instead.

**Organizr**, the closest off-the-shelf match for genuine tabs. It has no
native OIDC, so getting one login working would mean a forward-auth proxy
in front of it anyway — TinyAuth's whole job — plus a second app with its
own local user accounts, a fourth identity system next to Pocket ID, Open
WebUI's, and Konzol's.

**Homepage.** A good launcher, not a login gate: its iframe widget does not
proxy authentication, so it buys tabs but not the single sign-on that was
the actual point.

**Forking Open WebUI's frontend**, covered above. Rejected on cost, not on
feasibility — it would work, and cost more than this is worth.

### What would justify revisiting

If Open WebUI ever ships a genuine plugin surface for admin-panel pages, or
if Konzol's remaining responsibilities shrink enough that a page and a link
cover what's left of it. Until then, two surfaces behind one login is judged
close enough to the original ask to be worth the cost above.

## 23. The inference router, built ahead of the drift check decision #21 named first

Decision #21 ordered this explicitly: build the persona drift check first,
because it's what tells you whether the router delivers the uniformity it
exists for. Neither existed when this was requested directly, by name,
with an explicit instruction to build the router now. That instruction is
followed here, and the departure from the stated order is recorded rather
than silently taken — the reasoning in #21 for that order hasn't changed,
only the sequence it happened in.

### What this actually is

`router/config.yaml` and `router/persona_hook.py`: LiteLLM in front of
oMLX, injecting the persona from `prompts/` into every request for
`chat`, `deep`, and `ha-voice`, transparently — no client-side
`prompt_id`, no per-client system prompt field. Open WebUI and Home
Assistant switch to it by changing one port (`OWUI_INFERENCE_PORT`); the
model names they already ask for are unchanged.

**This is half of what #21 asked for, not all of it.** The other half —
"a verified user identity travels with the request, which is what makes
per-user memory routing possible" — is not built. The router today
injects a persona and nothing else; it does not read, forward, or act on
who is calling. Recorded plainly so this isn't mistaken for more than it
is: personas are now uniform across clients, and memory bank selection
still works exactly as it did before this, through Hindsight's own
per-connection URL scoping, unrelated to anything here.

### The mechanism, and why it isn't the one the docs recommend

LiteLLM's own documentation names `CustomPromptManagement` /
`get_chat_completion_prompt` as the tool for exactly this: a per-model
system prompt with no client-side parameter. It doesn't work in the
version this was built against (`ghcr.io/berriai/litellm`, pinned by
digest in `docker-compose.yml`). Not assumed — checked directly: the
class's own source
(`litellm/litellm_core_utils/litellm_logging.py`,
`get_custom_logger_for_prompt_management`) confirms it should fall back
to any registered `CustomPromptManagement` instance with no `prompt_id`
needed; a callback was registered exactly per LiteLLM's own reference
implementation
(`litellm/proxy/custom_prompt_management.py`); the module load was
confirmed with a debug print at import time; the method was never
invoked, confirmed by the same debug print never firing across repeated
real chat completions.

`async_pre_call_hook` — the older, plainer `CustomLogger` method used
everywhere for guardrails and rate limiting — does fire, verified the
same way. `router/persona_hook.py` uses that instead. Worth revisiting
if a future LiteLLM release fixes the newer API, since it's the
documented, intended mechanism and this is a workaround for it not
working, not a preference.

### The topology correction this build surfaced

Built against this deployment's real topology, stated directly rather
than assumed: **this installation is monolithic.** Open WebUI, Hindsight,
the console, and the Wyoming voice services all run on the same host as
oMLX. The only thing off-host is the reverse proxy fronting the portal
and Open WebUI, on a LAN-neighboring machine, not a VPS.

`docs/architecture.md`'s Placement section and `docker-compose.yml`'s own
header comment both said Open WebUI runs on a separate VPS, which was an
earlier plan, not this deployment — both corrected in the same change as
this router. Decision #15's public/private exposure model is deliberately
left untouched: it describes what may and may not face the internet,
which is a different question from which host runs which container, and
whether this deployment currently has any public exposure at all was not
confirmed one way or the other while building this. Marked VERIFY in
architecture.md rather than guessed.

### A real bug this surfaced, in already-merged code

The portal (#22) has the identical bug this router's own bind mounts hit
on first real deployment: `./portal/Caddyfile` and `./portal/index.html`
are relative paths, and compose resolves a relative bind against
`--project-directory`, which `up.sh` and `scripts/novak` both set to
`$NOVAK_HOME`, not the checkout. Docker's behaviour on a relative bind
whose source doesn't exist at that resolved path is to silently create an
empty directory there rather than error — so the failure doesn't surface
until the application inside tries to open the file and gets
`IsADirectoryError`, which is exactly what happened here on the first
real `novak up` with the router profile active. The portal has carried
this since #22 merged, undiscovered because nothing had run it through a
real `novak up` with that profile active end to end — the earlier testing
was container-level (`docker run` in isolation), which never exercises
compose's own path resolution.

Fixed for both: `REPO_DIR` is now exported by both `up.sh` and
`scripts/novak`, and every bind mount that needs the checkout — the
portal's two, plus this router's three (`config.yaml`, `persona_hook.py`,
and `prompts/`) — uses `${REPO_DIR}/...`, an absolute path, instead of a
relative one. Deliberately not seeded into `$NOVAK_HOME` the way
`registry/mcp-servers.yaml` is: that file is meant to be edited per
deployment, and these are read-only application config that should track
a `git pull` immediately, which a seeded copy would defeat.

### What was verified, end to end, not assumed

The full path, for real: `novak up` with `OMLX_API_KEY` already in the
Keychain correctly activated the router profile with no other
configuration; the real container started against the real
`docker-compose.yml`; a chat completion sent to it with no system message
came back answering as Novak, for `chat`, `deep`, and `ha-voice` all
three; a client-supplied system message was respected untouched, not
double-injected; a model name absent from the persona map passed through
with no system message added, as designed.

### What would justify revisiting

Doing the identity half of #21 — reading a verified caller identity and
making it available to per-user memory routing — is the obvious next
step and is not started. Building `router/config.yaml`'s model list by
hand also means it can drift from `registry/omlx.yaml` silently if a
model's underlying repo changes; a generator step alongside
`omlx_apply.py` would close that gap and hasn't been built. And the
persona drift check #21 asked for first is still exactly as un-built as
it was before this — this router does not verify its own claim of
uniformity, only asserts it.

## 24. `novak registry --check` does the reachability probing the reconciler deliberately doesn't

Prompted directly: a live deployment had two registry entries sitting at
`enabled: true` with `http://EDIT-ME:8888/...` as their URL for weeks —
`reconcile.py` only checks that a URL is syntactically real, never that
it's been edited — and the question that followed was whether the
reconciler should go further and check reachability, rather than pattern
match one placeholder string.

It shouldn't, and the reasoning is the same shape as #20's: a meaningful
reachability check needs the real auth token, since a bare unauthenticated
request can look identical to an authenticated one (Hindsight answers a
bare GET with `200 {}` either way — a handshake response, not a real
call, found directly while building this). Reading that token means
reading the Keychain, and `reconcile.py`'s own docstring already rules
that out on purpose: no secrets read, no network touched, no listener,
declare/apply only. Bolting a live probe onto it wouldn't extend the
reconciler, it would abandon what makes it safe to run unattended on
every `novak up`.

### Where it actually landed

`novak registry --check`, in `scripts/novak` — the CLI layer, where
reading Keychain secrets to test something is already normal
(`secret verify`, the deployment checklist's oMLX and Hindsight checks).
Plain `novak registry` is unchanged: fast, local, no network. `--check`
is opt-in, parses the reconciler's own `external: NAME -> URL [token:
VAR]` output rather than re-parsing the YAML a second time, and for each
entry with a token, reads it from the Keychain and sends one real MCP
call; entries with no token get a bare connection attempt.

The call sent is `initialize`, not `tools/list`. `tools/list` was tried
first and rejected after testing it live: streamable-HTTP MCP requires
session state from a prior `initialize` before it will answer anything
else, so an authenticated `tools/list` with no session returns `400
Missing session ID` — a false alarm, not a real signal, and standing up
the two-call handshake just to read a status code was more machinery
than this was worth. `initialize` needs no prior session and, confirmed
directly against the real deployment, genuinely flips: `401` with no or
the wrong token, `200` with the right one. That gives three distinct,
useful states — `200` really works, `401` reachable but not
authenticating (a wrong or missing Keychain value, not a dead host), and
a failed connection is neither.

### The bug this caught in its own first test

The first real test — an intentionally unreachable host — killed the
whole `--check` run instead of reporting one red line, because
`code="$(curl ... )"` with no `|| true` is a plain assignment, not a
condition, and `set -e` treats curl's own non-zero exit (28, timeout) as
fatal. `cmd_checklist`'s Hindsight check had already hit this exact shape
once (see its own comment, `scripts/novak`), and this reused the fix
without reusing the vigilance the first time around — worth noting
because it's the second time the same bash trap has shipped once and
been caught on the second write, not the first.

### What was verified, end to end

Against the real deployment: `outline-everything`, `hindsight-household`,
and `hindsight-tmeuze` all report `200`, genuinely reachable and
authenticating (the latter two only true after #23's follow-up fixed
their `EDIT-ME` placeholders to the real Tailscale address). A wrong
token against `hindsight-household` correctly reports `401`. A made-up
unreachable Tailscale address correctly reports `unreachable`, and —
after the `|| true` fix — does so without aborting the rest of the
entries.

## 25. The router's `task` model: Open WebUI's background calls get a persona bypass

Reported directly: Open WebUI got noticeably laggier since the router
went live. Root cause, confirmed rather than guessed at — Open WebUI's
Task Model setting (Admin Settings -> Interface -> Tasks) defaults to
"Current Model" for title generation, tag generation, and follow-up
suggestions, all three on by default. "Current Model" means whatever the
user is actively chatting with — `chat` or `deep` — which since #23 now
goes through the router and gets the full persona injected on every
single call, `persona_hook.py`'s `PERSONA_MAP` making no distinction
between a real conversational turn and a three-word title nobody reads
as a conversation.

Measured directly, not estimated: the identical trivial request
(`"Reply with exactly one word: hello"`) cost 574 prompt tokens and
2.13s through `chat`, against 15 prompt tokens and 0.34s through the new
`task` model below — on an already-warm model, so a cold `deep` (idle
TTL expired, thinking on) paying this same tax would be worse still.

### The fix

`router/config.yaml` gets a fourth `model_name: task`, aliasing the same
underlying oMLX model and profile `ha-voice` already uses — always
resident (no TTL wait), thinking off, tuned for short low-creativity
output, which is exactly the shape title/tag/follow-up generation needs.
Deliberately **not** added to `persona_hook.py`'s `PERSONA_MAP`, so the
hook no-ops for it by construction rather than by a special case.

Open WebUI's Local **and** External Task Model (both — its own docs
don't fully specify which applies to an all-OpenAI-API setup with Ollama
disabled, and setting both costs nothing) are pointed at `task` in the
admin UI. That alone doesn't survive a restart: `ENABLE_PERSISTENT_CONFIG`
is `false` on purpose (`docker-compose.yml`'s own comment explains why —
this exact instance already lost a config change to a restart once,
silently, before that flag existed), so `TASK_MODEL` and
`TASK_MODEL_EXTERNAL` are also set directly in `docker-compose.yml`,
gated behind a new `OWUI_TASK_MODEL` .env key that defaults to blank —
correct when the router isn't configured at all, since `task` isn't a
model name anywhere else in that case.

### What this surfaced, unrelated to the fix itself

Open WebUI has no `WEBUI_SECRET_KEY` pinned anywhere in this stack — it
generates a random one at container startup when unset, which
invalidates every existing session on every restart. Confirmed directly:
recreating the container to apply this very fix logged out the admin
session that was open to verify it. Flagged as its own follow-up rather
than folded in here — a session-signing key is an unrelated concern from
a task-routing one, and conflating them in one change would make either
harder to revert independently if something about it needed undoing.
Fixed in #26 below.

### What was verified, end to end

The `task` model shows up in Open WebUI's own model dropdown only after
a router restart (it caches the model list at page load, not on every
request — a stale list is expected, not a bug, after adding one).
`TASK_MODEL`/`TASK_MODEL_EXTERNAL` confirmed set correctly inside the
running container via `docker exec`, after a real `novak up` recreate,
not just in the admin UI which alone wouldn't have proven persistence.

## 26. Open WebUI's session key gets pinned, the same way CONSOLE_AUTH_SECRET is

Confirmed directly: a routine `novak up` recreate of the `open-webui`
container logged out an active admin session — the same symptom #25
flagged as a follow-up rather than fixing inline.
`docker-compose.yml` never set `WEBUI_SECRET_KEY`. Open WebUI signs
its session JWTs with that key and, left unset, generates a random one
at every container startup — so a restart or recreate doesn't just
*eventually* expire sessions, it invalidates every one of them
immediately, since the JWTs on file no longer verify against the new
key.

Fixed by adding `WEBUI_SECRET_KEY` to `SECRET_VARS` in
`scripts/lib/vars.sh` and sourcing it from Keychain exactly the way
`CONSOLE_AUTH_SECRET` already is — generated with `openssl rand -base64
32`, never edited into `.env` directly. Not added to `CORE_SECRETS`:
left unset, the stack still starts, `set-in-keychain` gets passed
through as a literal value, and Open WebUI just logs everyone out on
every restart, the same degrade-not-block shape as every other
non-core secret here.

**Verified end to end:** `novak secret set WEBUI_SECRET_KEY --generate`,
then `novak up`, then `docker exec novak-open-webui-1 sh -c 'echo
$WEBUI_SECRET_KEY'` — non-empty, and identical across repeated checks
and after `novak restart open-webui`. A login made before the restart
was still valid after it.

## 27. Open Terminal joins the registry as the first `container` entry that isn't MCP

Requested directly, as an explicitly optional, opt-in integration —
consistent with how everything else in `registry/mcp-servers.yaml` works.
[Open Webui's Open Terminal](https://github.com/open-webui/open-terminal)
(Apache-2.0) is a sandboxed terminal and file browser a model can be
given access to from Open WebUI's own Admin -> Settings -> Integrations.

It doesn't speak MCP. Open WebUI connects to it directly as an
"Integration," not through the MCP client wiring every other registry
entry assumes. Checked `reconciler/reconcile.py` before assuming this was
a problem: `render()` doesn't care what a container speaks, only that it
has an image, a port, and declared env vars — the "MCP server" framing
in the registry's header comment was descriptive, not a constraint the
mechanics actually enforce. Landed as `kind: container` with a comment
correcting the record, rather than inventing a new `kind` for one entry.

### Two limits chosen deliberately, not defaults left alone

This is `risk: dangerous` by the registry's own definition — it runs
arbitrary code and reads/writes a filesystem, no reading between the
lines required. Shipped disabled, no `accepted_by`/`accepted_on`, same
as `ha-mcp` — the reconciler refuses to start it until a person accepts
that in the record.

Two things Open Terminal's own docs offer that this entry deliberately
does not:

- **No Docker socket mount.** Its README documents one for letting an
  agent manage other containers, and its own words for what that grants
  are "effectively root access." Nothing about this stack needs a model
  that can start or stop its own containers, so it isn't offered.
- **No filesystem mount into anything real.** Left on the image's own
  default scratch space. A model reading its own sandbox is the
  intended use; a model reading this repo, `$NOVAK_HOME`, or any secret
  is not, and nothing here grants that path.

Neither is a technical limitation being worked around — both are
choices about what doesn't get added later without the same scrutiny
turning this on in the first place got.

### What was verified before shipping

The registry entry validates and reports `disabled` (correct — it's off
by default). Test-enabled with a dummy key and a filled-in
`accepted_by`/`accepted_on` against a scratch `$NOVAK_HOME`, the
reconciler correctly renders a real `open-terminal-mcp` service (the
`-mcp` suffix is `render()`'s own hardcoded naming, cosmetically wrong
for a non-MCP entry, not worth changing for one container), with the
image, `8010:8000` port mapping, and `OPEN_TERMINAL_API_KEY` passed
through from the host environment — the same path every other container
entry already uses, unmodified for this one.

## 28. Novak becomes multi-platform: Mitochon (Mac) stays fully supported, Spire (Unraid/RDNA4) becomes the primary reference deployment

This is the pivot everything up to #27 was, unknowingly, already built to
survive. Recorded here as a deliberate decision because it is one — not a
drift nobody wrote down.

### What actually changed

The household is moving its day-to-day Novak deployment onto Spire, an
Unraid box already running a dozen other services, freshly given an AMD
Radeon RX 9060 XT (RDNA4). Mitochon — the Mac mini every prior decision
in this file assumed — goes back to being a regular, always-on computer.
It keeps oMLX as a secondary inference engine other clients can point at
deliberately (Open WebUI's own model config, or a future Novak router
entry), but it is no longer the host anything in this stack depends on
being up.

**Nothing already built for Mitochon is deleted or deprecated.** Novak
was a single-platform project pretending to be general; this makes it
actually general. `docker-compose.yml`, `registry/omlx.yaml`,
`omlx-settings.md`, `headless-operation.md` — every one of them stays,
intact, as one complete, real deployment path. What changes is that it
stops being *the* path and becomes *a* path, chosen at setup rather than
assumed by the code.

### Why this was less work than it sounds

Checked before assuming a rewrite was needed: almost nothing about
Hindsight, Open WebUI, the console, or the Wyoming voice services is
macOS-specific. They're plain containers. The *only* piece of Novak that
ever genuinely needed to be a Mac was oMLX itself — a native app because
Metal/MLX can't run in a Linux container. Once that's understood,
"Novak on Linux" was never really the hard problem; "oMLX specifically
needs a Mac" is a fact about one engine, not about the whole stack.

That reframes the whole architecture cleanly:

- **Novak core** (Hindsight, Open WebUI, the console, voice, the
  registry/reconciler pattern, the router) — a Docker Compose stack that
  runs on any real Docker host. Spire, tonight, proved this directly:
  everything that isn't inference is ordinary containers on ordinary
  Linux.
- **Inference engines** — pluggable, behind the router, each on whatever
  host actually suits it. oMLX/Mitochon (macOS, Metal) and
  Ollama/Spire (Linux, Vulkan/RDNA4) are the first two, documented as
  parallel siblings, not a primary and a workaround.

The router (#21/#23) already had the right shape for this by accident:
`router/config.yaml`'s `api_base` is just an OpenAI-compatible endpoint,
with no assumption baked in about what serves it. It needed no rework at
all for this pivot — the pieces that did were the ones that had never
been asked to be portable: `bootstrap.sh`, the registry's oMLX-specific
assumptions, and every doc that said "your Mac" where it meant "your
inference host."

### What Mitochon's reduced role actually retires

`headless-operation.md`'s entire FileVault/JetKVM/unattended-recovery
apparatus existed to solve one problem: a host that MUST come back up on
its own after a power cut, because everything depends on it. That
problem is Spire's now, and Spire is a Linux server — it doesn't have
any of the constraints that apparatus exists to work around (no
WindowServer-requires-a-login-session, no per-account OrbStack
isolation, none of it). Mitochon, once it's a "regular computer,"
doesn't need FileVault-unlock-via-KVM either — if it's off or asleep,
oMLX just isn't available as a secondary engine until someone's using
the machine anyway, which is a fine, low-stakes failure mode for
something optional.

**Not deleting `headless-operation.md`.** It stays as exactly what it
always was — real, hard-won, and correct for anyone who *does* want
oMLX/Mitochon to be their primary, always-up engine, which is a
completely legitimate choice for someone without a spare Linux box.
It's just no longer the assumed path in this household's own deployment,
and the docs need to stop reading as if it were the only one.

### What this asks of the setup scripts and docs going forward

Not built yet — this decision records the shape, not the finished
implementation:

- `bootstrap.sh` (and the `novak` CLI more broadly) need a real "which
  platform, which engine" choice at setup time, instead of assuming
  macOS + OrbStack + oMLX throughout.
- Each engine gets its own settings doc, sibling to `omlx-settings.md`
  — Spire's Ollama/RDNA4 setup needs the same kind of "here's the real
  reasoning for these numbers" treatment `omlx-settings.md` already
  gives the Mac path, not a paragraph bolted onto an existing doc.
- `README.md` and `docs/architecture.md` currently read as if "your Mac"
  and "Novak's inference host" are the same sentence. They need to stop
  saying that.

### What was verified before recording this as settled, not aspirational

Real, on Spire, tonight: GPU passthrough into Docker with a plain
`--device=/dev/dri`, no vendor plugin needed; Ollama detecting the 9060
XT correctly via Vulkan (`RADV GFX1200`); real generations on `qwen3:4b`
(94.8 tok/s) and `qwen3:14b` (32.6 tok/s), both fitting entirely in the
card's 15.9GB VRAM. Qwen3.8-27B does not fit (confirmed via `ollama ps`
showing a genuine 12%/88% CPU/GPU split even in isolation, ~10 tok/s) —
recorded honestly as the reason it stays on Mitochon/oMLX rather than
forced onto hardware that doesn't fit it well.

### What would justify revisiting

Getting real speed out of Qwen3.8-27B on Spire specifically would mean
running raw `llama-server` with native MTP speculative decoding
(`--spec-type draft-mtp`) instead of Ollama — confirmed directly that
Ollama's own MTP support exists only on its MLX runner today, not the
Vulkan/AMD backend. That's real, documented, and deliberately not done:
it would mean a second inference engine's worth of lifecycle and
multi-model complexity to speed up exactly one model, when Mitochon
already serves it acceptably. Revisit if Qwen3.8-27B specifically
becomes important enough to justify that.

## 29. `registry/engines.yaml` + `reconciler/router_apply.py`: the multi-engine setup script decision #28 named as still missing

Decision #28 recorded the direction and named the gap plainly: hand-editing
`router/config.yaml` to add a second engine "is the real next piece of
code, not just docs." This is that piece.

### The mechanism

Same shape as `registry/mcp-servers.yaml` and `registry/omlx.yaml`: a
declarative file, a dumb reconciler, git as the audit log. Each engine
declares a `base_url_var`/`api_key_var` (variable *names* — no secret is
ever read here, same invariant `reconcile.py` holds) and a list of
`{role, model}` pairs. `router_apply.py` validates it (a role claimed by
two engines is refused outright — ambiguous routing, not load-balancing)
and renders `router/config.yaml`'s `model_list`. It does not restart the
router; same reasoning `novak omlx apply` already uses for not silently
restarting oMLX — a visible, separate `novak restart router` step.

### The bug this design caught in itself before it shipped

`router/config.yaml` was, until this decision, a tracked repo file *and*
needed to become a per-deployment generated artifact — genuinely
incompatible. A real deployment running `novak router apply` would dirty
a tracked file with household-specific model IDs on every run. Fixed by
treating it exactly like `docker-compose.mcp.yml` already is: pure
generated output in `$NOVAK_HOME` (`router-config.yaml`), gitignored,
never in the checkout. `docker-compose.yml`'s router mount changed from
`${REPO_DIR}/router/config.yaml` to a relative `./router-config.yaml`,
resolving against `--project-directory` the same way `./registry`
already does. The checked-in `registry/engines.yaml` is now a genuine
generic template (single oMLX engine, matching how a fresh deployment
actually starts) — the real, household-specific multi-engine config
lives only in `$NOVAK_HOME`'s deployed copy, same rule
`headless-operation.md` already states for `mcp-servers.yaml`.

### Two real bugs found running this end to end, neither in the new code

Testing every model role through the actual router (not assumed working
from the dry-run render) surfaced both:

- **`qwen3:14b` on Spire returned "does not support chat"** despite
  `ollama list` showing it present and a real generation having worked
  on it hours earlier. Root cause: pulling it and the Qwen3.8-27B model
  concurrently earlier that session raced on Ollama's blob/manifest
  store, leaving the server's in-memory model-capability cache stale.
  Fixed with `ollama rm` + a clean re-pull, **then a container restart**
  — the first restart (before the re-pull) wasn't enough, since it
  restarted against the still-corrupted manifest.
- **`deep` pointed at Qwen3.8-27B on oMLX, which was never actually
  downloaded there.** All of that model's testing this session happened
  on Spire/Ollama; nothing had put it in oMLX at all. oMLX correctly
  404'd it — the router mechanism worked exactly right, the registry
  entry was simply wrong. Fixed by pointing `deep` at the existing,
  working `Qwen3-14B-4bit:deep` profile as an honest interim, with a
  comment recording that Qwen3.8-27B-on-oMLX is a real, separate,
  not-yet-done task — not silently reverted without a record of why.

Neither bug was in `router_apply.py` or the registry schema. Both were
caught specifically *because* every role was tested against the real
running router, not just validated against the schema and assumed
correct from there.

### What was verified before calling this done

All four model roles (`chat`, `deep`, `ha-voice`, `task`) return real
200 responses through the actual router, hitting both engines
(`omlx-mitochon` for `deep`, `ollama-spire` for the other three) — not
just a dry-run render. `task`'s response carries 17 prompt tokens,
confirming persona injection is still correctly bypassed for it exactly
as decision #25 intended, unaffected by which engine now serves it.

## 30. `DEFAULT_ENGINE_BASE_URL` is a real `.env` value now, not a `host.docker.internal` construction

Two problems, raised directly while actually standing up Spire's own
deployment, both pointing at the same fix.

(Named `OMLX_BASE_URL` for about twenty minutes before this was written
down — caught before Spire's own deployment locked it in: a variable
meaning "the default engine, whatever it is" named after one specific
engine is exactly the kind of thing that reads fine on the machine that
has that engine and actively misleads on the one that doesn't, which
Spire — no oMLX at all — was standing right there to prove.)

**`host.docker.internal` isn't something to build behavior around by
default.** It needs Docker's `host-gateway` `extra_hosts` entry to work
at all outside macOS/Docker Desktop — present everywhere it's used here,
and confirmed genuinely working on Linux/Unraid tonight, so this was
never actually broken. But baking a `host.docker.internal`-based URL
into `docker-compose.yml` as the *default*, three separate times
(Open WebUI, Hindsight, the router), each with its own port-fallback
chain, meant "where's the engine" was a fact spread across compose
interpolation rather than a fact you could read in one place.

**Most configuration should live in `.env`, not in compose interpolation
logic.** `OWUI_INFERENCE_BASE_URL` and `HINDSIGHT_LLM_BASE_URL`, added
earlier this same session to handle a remote router, were themselves a
symptom: they existed only because the *default* (`DEFAULT_ENGINE_BASE_URL`, in
effect) wasn't itself a plain value — it was a port number
(`OWUI_INFERENCE_PORT`) glued to `host.docker.internal` inside the
compose file. Fixing the override without fixing the default underneath
it would have left two mechanisms doing the same job.

### The fix

`DEFAULT_ENGINE_BASE_URL` is now a real, complete URL, set directly in `.env`
(default `http://host.docker.internal:8000/v1` — right for the common
single-host case, same as always, just no longer built at compose-parse
time). Open WebUI, Hindsight, and the router all fall back to it
directly. `OWUI_INFERENCE_PORT` is removed outright, not deprecated
alongside it — this project's own README still says "in testing," and
carrying two mechanisms for the same setting past the point one of them
is clearly worse serves no one. `OWUI_INFERENCE_BASE_URL` and
`HINDSIGHT_LLM_BASE_URL` remain, now as genuine overrides *of*
`DEFAULT_ENGINE_BASE_URL` rather than overrides of a `host.docker.internal`
construction — the same variables, a cleaner reason to have them.

The router's own `DEFAULT_ENGINE_BASE_URL` entry in `docker-compose.yml` was
deleted rather than simplified: decision #29's `env_file` fix (this same
session) already passes the whole `.env` through to the router
container, so a value that's now a plain `.env` literal needs no
`environment:` entry to also provide it. One less place the same fact
could go stale.

### What was verified before treating this as done, not just tidier

Every one of Mitochon's three affected services was checked against the
*resolved* value inside the actual running container, not just the
`docker compose config` render: `HINDSIGHT_API_LLM_BASE_URL` and
`OPENAI_API_BASE_URL` both came back identical to their pre-refactor
values (`http://host.docker.internal:8000/v1` and `:4000/v1`
respectively) — this was a mechanism change, not a behavior change, and
that claim was checked, not assumed. A real chat completion through the
router still returned a real answer afterward.

## 31. The port defaults move to a clustered block, after a real collision

Every service's default port used to be whatever its own upstream
project happened to pick — 3000, 3002, 4000, 8000, 8199, 8888, 9999,
10200, 10300, 10400, 3003, scattered across the whole range with no
relationship to each other.

Standing up Spire surfaced the actual cost of that directly: Hindsight's
default `8888` collided with an existing, unrelated container on the
same box (a VPN gateway), which is a coincidence but not a surprising
one — `8888` is a common enough default elsewhere that this was always
going to happen to *someone*, on *some* host running more than one
self-hosted thing, which describes most of the hosts this project asks
someone to run it on.

### The fix

`.env.example`'s defaults move to a contiguous, uncommon block —
`13400`-`13409` — one thing to remember, firewall, or document instead
of ten scattered numbers, and far less likely to collide with whatever
else a given host already runs. Only the *template's* defaults change;
an existing deployment's real `.env` already has its own explicit
values and is untouched regardless of what a fresh clone's `.env.example`
now says.

**Not a full sweep of every doc that mentions a specific port number.**
`docker-compose.yml`'s own comments and `docs/proxy.md` — the one just
handed to this household as real, copy-pasteable Caddy config — are
updated. `architecture.md`, `cli.md`, `home-assistant.md`,
`memory-setup.md`, `how-memory-works.md`, `deploy-checklist.md`, and
`security.md` still cite the old numbers in places. Recorded honestly as
open, not silently left stale: a real, tracked follow-up, not a claim
that this decision finished a sweep it didn't attempt.

## 32. `env_file` reads `.env`'s literal text — which is exactly why a secret can't come from it

Decision #29's `env_file` fix worked on Spire and shipped without
catching what it broke on Mitochon, because Spire's only engine needs no
secret at all — the bug had nothing to trigger it there.

### What actually happened

Mitochon's `deep` role started returning `litellm.AuthenticationError:
Incorrect API key provided: set-in-k***hain` — the literal placeholder
text from `.env`, not a real key. `env_file:` reads a file's on-disk
lines directly; it has no way to see the real Keychain value `up.sh`
resolves and exports into its *own* process environment — the exact
mechanism that already makes `${OMLX_API_KEY:-none}` correctly resolve
everywhere else in this file, via compose-file interpolation, which is a
genuinely different substitution pass than what `env_file:` does. A
secret's `.env` line is deliberately never the real value (that is the
entire point of Keychain), so `env_file:` can only ever hand the router
the placeholder for one. Compounding it: the same deployment's registry
still said `base_url_var: OMLX_BASE_URL`, a name retired by decision #30
— `os.environ/OMLX_BASE_URL` resolved to nothing, and LiteLLM silently
called real OpenAI's endpoint with the placeholder as a bearer token,
which is where the confusing error text came from.

### The fix, and why it isn't a retreat from decision #29

`environment: - OMLX_API_KEY` (bare name, no value) sits alongside
`env_file: - .env` on the router. Compose's own precedence rule —
`environment:` wins over `env_file:` for the same key — means this one
name now comes from the calling process's real, Keychain-resolved
export instead of the file. Everything else (base URLs, any future
engine's `base_url_var`) still needs no code change here, which was
decision #29's actual point and remains true.

**This isn't the allowlist decision #29 removed, reintroduced.** That
allowlist enumerated *every* variable a future engine might need,
including ones with no reason to ever be a secret. This enumerates only
secrets — and a new secret already, unconditionally, requires a line in
`SECRET_VARS` (`scripts/lib/vars.sh`) before it works anywhere in this
stack. Requiring a matching line here too is the same existing
constraint reaching one more place it had a gap, not a new one.

### Also cleaned up while tracing this

Mitochon's own `registry/engines.yaml` still had the mid-session,
cross-host shape (`omlx-mitochon` for `deep` + `ollama-spire` for
everything else) from before "Spire runs the entire stack, independent
of Mitochon" was stated as the actual direction. Reverted to a clean,
single-engine `omlx` registry, matching what Mitochon's own real role
now is. Spire's `OLLAMA_LOCAL_BASE_URL` was consolidated into
`DEFAULT_ENGINE_BASE_URL` (they pointed at the identical value; two
names for one fact was exactly the sprawl that prompted this whole
review), and `OLLAMA_SPIRE_BASE_URL` — dead on both hosts once neither
registry referenced it — removed everywhere, including as a
household-specific example baked into the checked-in `.env.example`
template, which a generic instruction about adding a second engine
replaced.

### What was verified before calling this fixed

All four roles (`chat`, `deep`, `ha-voice`, `task`) re-tested with real
generations on Mitochon after the fix — not just the one that was
broken — plus the container's actual `OMLX_API_KEY` env var checked
directly (`sk-omlx-...`, not the placeholder) before trusting the
symptom was gone rather than just quieter.

## 33. Storage reorg on Spire, and Ollama folds into docker-compose.yml as a profile-gated service

Follow-up to decision #28/#31, once Spire was confirmed as the primary,
sole-host deployment (Mitochon taken down as a server, kept only for
oMLX development). Two separate but related changes, both requested
together:

### The storage split

Novak's compose manifests, `.env`, and Compose Manager's own project
state stay exactly where they were — `/mnt/cache/appdata/stacks/Novak/`
— since Compose Manager's `projectDirectory` is always derived from
wherever the compose file itself lives (confirmed by reading
`Util.php`'s `StackInfo::buildComposeArgs()` directly), so moving the
manifests would mean re-registering the whole project.

Everything else Novak owns — config the reconciler writes
(`registry/`, `router-config.yaml`, `wakeword/`), and (as of this
decision) service databases, media, and model weights — moves to
`/mnt/teracache/Novak/{config,data,models}`. Config already done: moved
physically, with a symlink left at the old path inside the stacks
directory, so nothing that reads `./registry` or `./router-config.yaml`
(relative to `--project-directory`) needed to change at all.

The service data directories (Hindsight's Postgres, Open WebUI's
`webui.db`/uploads/vector DB, Whisper/Piper's model caches) use a new
`${SERVICE_DATA_DIR:-namedvolume}` pattern instead: unset, a service
keeps using its existing Docker-managed named volume (Mitochon's
default, and any other single-disk deployment's); set to a real host
path, Compose treats it as a bind mount instead — no other code
difference, since Compose decides bind-mount-vs-named-volume purely
from whether the volume's source string matches a declared top-level
`volumes:` key. `OWUI_DATA_DIR`, `HINDSIGHT_DATA_DIR`, `WHISPER_DATA_DIR`,
`PIPER_DATA_DIR`, `OLLAMA_DATA_DIR` were added to `.env.example`, all
blank by default — a zero-risk no-op for any deployment that never sets
them.

### Ollama joins docker-compose.yml

Previously a standalone Compose Manager project on Spire
(`/mnt/teracache/appdata/Ollama/`), set up ad hoc while decision #28 was
first being verified and never folded back in — flagged directly by the
user mid-session ("there is also an 'ollama' container seemingly
standalone... it is not custom, but it is still a part of the
compose/stack regardless"). Folded in now as a new `ollama` service,
gated behind its own `profiles: ["ollama"]` — same pattern as
`router`/`console`/`portal` — so a host running oMLX (Mitochon) never
starts a second, unused inference engine, and nothing changes for a
deployment that doesn't opt in.

Settings replicated exactly from the standalone project's real,
working config (`/dev/dri`+`/dev/kfd` passthrough, `OLLAMA_VULKAN=1`,
`OLLAMA_MAX_LOADED_MODELS=2`, `OLLAMA_NUM_PARALLEL=4`,
`OLLAMA_KEEP_ALIVE=20m`), each now overridable via `.env` rather than
hardcoded, matching every other service in this file. Its data volume
uses the same `${OLLAMA_DATA_DIR:-ollama}` pattern as the storage
split above — pointed at `/mnt/teracache/Novak/models/ollama` on
Spire once the actual model data is moved there from the old
standalone project's directory.

### What was completed as follow-up, same day

All four items this decision originally left open are now done and
verified: Hindsight's/Open WebUI's/Whisper's/Piper's live data moved
into the new bind-mount paths via the helper-container pattern (real
data confirmed intact — 244 Open WebUI chats, Hindsight responding
healthy — before the old `novak_*` named volumes were deleted); Ollama's
model weights moved and the old standalone project decommissioned;
`UD-IQ4_XS` pulled, confirmed 100% GPU-resident (`ollama ps`, no CPU
offload) at 19.43 tok/s versus the old `UD-Q4_K_M`'s ~10 tok/s on a
12%/88% split, and set live as the `deep` role, verified end to end
through the router. See [ollama-settings.md](ollama-settings.md) for
the numbers.

## 34. Portal/TinyAuth stay off on Spire — the VPS already does this job

The `portal` compose profile bundles Caddy (the single-page tabs
frontend) and TinyAuth (forward-auth gating it) together, since Caddy's
own `Caddyfile` hard-codes `forward_auth tinyauth:3000` — there's no
state where one runs without the other today.

Spire doesn't need its own copy: the user's public VPS already runs
TinyAuth for this purpose. Rather than leave Caddy running with a
forward-auth backend that doesn't exist (a 502 on every request, not a
graceful "auth not configured" state), the whole `portal` profile was
turned off on Spire — Compose Manager's `profiles` file there no longer
lists it, and the running `caddy`/`tinyauth` containers were stopped and
removed. Nothing in `docker-compose.yml` itself changed; both services
stay defined and gated behind `profiles: ["portal"]` exactly as before,
for any deployment that does want a local instance.

If a future need arises to run the portal's Caddy on Spire without a
*local* TinyAuth (e.g. gated by the VPS's TinyAuth instead, over
Tailscale), that needs `tinyauth` split into its own profile and the
Caddyfile's `forward_auth` target changed — not attempted here, since it
wasn't asked for and changes the actual trust boundary, not just which
process runs it.

### Also recorded this round, not yet acted on

- **Coral TPU (`/dev/apex_0`) is reserved for Frigate**, not attempted
  for LLM inference (confirmed earlier, decision #28's investigation,
  that it's architecturally incapable of that anyway). Frigate isn't
  deployed yet.
- **Frigate ⨯ Ollama integration** wanted once Frigate exists — likely
  Frigate's own generative-AI description feature pointed at Ollama's
  OpenAI-compatible endpoint, or a registry entry once that's real
  rather than aspirational. Not designed yet.
- **Home Assistant is not set up on Spire at all yet.** Named as a next
  step, not started. `docs/home-assistant.md` describes wiring the
  Wyoming voice services and the router to HA; none of it has been
  applied against a real HA instance on this host.
- **`novak` CLI support for Unraid** — see decision #35, started the
  same session this was recorded.

## 35. `novak` CLI works on Unraid — same commands, two platform-specific parts

Decision #28 made Spire the primary deployment; every real config change
against it this session before now went through raw SSH commands and
Compose Manager, never `novak` itself, because the CLI hard-depended on
macOS's Keychain (`security`) everywhere it touched a secret. Named as an
explicit open item in that decision's follow-up audit, and asked for
directly: "Implementing `novak` cli in Unraid would be a great move. It
must follow the same principles - eg. `novak adopt` pulls from git and
merges new codebase, etc."

**The design constraint that mattered most: one CLI, not two.** A separate
`novak-unraid` script would drift from `scripts/novak` the moment either
one changed — exactly the sprawl this whole project keeps refusing (see
#6, #29). So `scripts/novak` itself became platform-aware
(`PLATFORM="$(uname -s)"`), and the two genuinely-different pieces were
pulled into their own file, `scripts/lib/secrets.sh`, sourced by both
`scripts/novak` and `scripts/up.sh`:

- **Secret storage.** Darwin keeps using the Keychain exactly as before.
  Linux has no OS keychain to use headlessly — Unraid never has a
  logged-in desktop session to unlock one — so `secret_set`/`secret_get`
  read and write the real value directly in `.env` there instead, which is
  already what Spire's actual deployed `.env` does today (confirmed by
  reading it directly: `OMLX_API_KEY`, `HINDSIGHT_API_KEY`, etc. are real
  values, not placeholders). This is a genuinely LOWER security bar than
  Keychain — said so in the file, not disguised as an equivalent — traded
  for something that works unattended on a platform with no per-user
  session at all. File permissions (600, enforced by `secret_set` on every
  write) are what stands in for Keychain's OS-level encryption; there's no
  second factor. `novak secret verify` gained a Linux-specific permissions
  check (`secret_permcheck`) as the closest equivalent to Darwin's
  "would this hang an unattended boot" check, since a plain file read
  can't hang the way a Keychain auth dialog can.
- **Where the CLI is linked from, and `NOVAK_HOME`'s default.** Confirmed
  directly on Spire before writing this: Unraid's `/` and `/usr` are a
  RAM-based overlay rebuilt from the flash image (`/boot`) on every boot —
  `mount` shows `rootfs` and an `overlay`, and nothing outside `/boot` or
  `/mnt` survives a reboot. `/usr/local/bin/novak` would vanish at the next
  one unless something re-creates it, so `scripts/bootstrap-unraid.sh`
  (new, root-only, no admin/service-account split the way macOS's
  bootstrap.sh/bootstrap-admin.sh needs — Unraid has exactly one real
  admin account) adds a line to `/boot/config/go` that does exactly that.
  `NOVAK_HOME` can't default to `$HOME` (`/root`) the way it does on macOS
  either: Compose Manager's `projectDirectory` is always derived from
  wherever `docker-compose.yml` itself lives (confirmed earlier this
  session by reading its `Util.php` directly), so `NOVAK_HOME` has to be
  that exact path — bootstrap-unraid.sh asks once and persists the answer
  to `/boot/config/novak/novak_home`; `scripts/novak` and `up.sh` both read
  it from there when the environment variable isn't set.

### Smaller platform seams, same pattern throughout: detect, don't guess

- Tailscale's control socket is at a different path on Unraid
  (`/var/run/tailscale/tailscaled.sock`, confirmed directly) than macOS
  (`/var/run/tailscaled.socket`) — `novak ports` checks both.
- The OrbStack per-account-VM ownership check in `novak ports` is
  Darwin-only; Unraid runs one Docker daemon as root for the whole host,
  so there's no per-account split to misdiagnose.
- `novak omlx apply` refuses outright on Linux with a pointer to
  `novak router apply` instead — Metal/MLX cannot run there at all
  (decision #28), so pretending otherwise would just produce a confusing
  failure two layers down instead of a clear one here.
- The checklist's Phase 1 (admin setup) and Phase 10 (unattended
  operation) needed real Unraid-specific checks, not macOS ones run
  uselessly: array auto-start (`/boot/config/disk.cfg`) instead of
  FileVault/`pmset`, and Compose Manager's own per-project `autostart`
  file plus the `/boot/config/go` persistence line instead of a
  LaunchAgent. Phase 4's model check now hits `DEFAULT_ENGINE_BASE_URL`'s
  `/v1/models` on Linux instead of `OMLX_PORT` — confirmed directly that
  Ollama serves the identical OpenAI-compatible shape oMLX does, so the
  existing parsing logic needed no changes, just a different URL.
- `compose()` (the function every `novak` subcommand funnels through)
  reads Compose Manager's own `profiles` file on Linux when present,
  rather than a second hardcoded profile list that could drift from what
  Compose Manager itself believes is active.

### What this deliberately does NOT do

`novak adopt`, `novak drift`, `novak config`, and the reconciler applier
commands (`omlx apply` aside) needed **no changes at all** — they were
already OS-agnostic (git, python3, plain file edits), which is exactly
what "same principles" meant in practice: the platform-specific work was
entirely in secret storage and host wiring, not in the actual behaviour
those commands provide. `bootstrap-unraid.sh` does not attempt to
register the Compose Manager project itself — that's a one-time,
UI-driven step better done deliberately (Docker tab -> Compose Manager ->
Add New Stack -> Indirect Config File) than guessed at by a script running
unattended against a real host's plugin state.

Not yet done, tracked as follow-up: run bootstrap-unraid.sh for real on
Spire and verify every command end to end (this decision records the
design and the code, not a live-tested deployment); decide whether
`scripts/reset.sh`'s destructive-operation guards need a Linux path at
all, given Spire's real data now genuinely matters (unlike the
"development phase, no production data" framing decision #28 opened with).
