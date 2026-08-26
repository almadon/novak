# Adding an agentic capability to Novak: a decision tree

**Status: evaluation only.** Nothing on this page has been adopted. No
registry entry exists for any option named here, and nothing has been
installed. This is a framework for the next time this question comes up,
plus the findings from the first time it did, on 2026-08-26.

## The question this answers

"Chat with a model" and "let something take real actions: edit files, run
shell commands, call tools with side effects" are different capabilities,
and Novak's existing registry (`registry/mcp-servers.yaml`) was built
around the first one and services that expose scoped, read-mostly tools.
Adding something closer to a coding agent (Claude Code, OpenCode,
OpenHands, or whatever comes after them) doesn't fit that shape cleanly,
and re-deriving the trade-offs from scratch each time one of these comes up
is exactly the kind of settled question [decisions.md](decisions.md) exists
to avoid re-litigating. This is that document for the coding-agent case
specifically, walking the same way `registry/mcp-servers.yaml`'s risk
levels do, but for a bigger category of thing.

## The tree

**1. Does this need real actions, not just chat?**

If a model answering questions is enough, stop here. Any chat model, local
or cloud, is a `standard`-risk registry addition: the same shape as
adding an oMLX profile, no special handling. See "Plain chat" below.

If yes, continue.

**2. Does it need to run against a local model, or is a cloud provider
acceptable for this specific capability?**

This is a real fork, not a preference. Novak's stated position is that
nothing you say to it leaves your machines by default; an agentic
capability is a deliberate, named exception to that, made per
capability, the same way [security.md](security.md) rule 5 requires
public exposure to be an individual, recorded decision rather than a
default.

- **Local-only required or preferred** → OpenCode or OpenHands, pointed at
  oMLX. See "Local agent frameworks" below.
- **Cloud acceptable for this one thing** → Claude Code, via an existing
  Open WebUI pipe. See "Claude Code" below.

**3. Whoever gets access to it, is it everyone in the household or just
one person?**

This determines both the credential mechanism and whether Open WebUI's
native model-level RBAC needs to be configured, covered in its own
section below because it applies to every option on this tree, not just
one branch.

**4. Where does the risk classification land?**

Every option here is `dangerous` by the registry's own definition:
"can change the machine or the stack itself: edit config files, read
arbitrary files, run code." That's not a reason to avoid all of them, it's
the reason none of them get the informal treatment a read-only MCP tool
gets. See "Risk classification" at the end.

---

## Plain chat

If capability #1 is "no," Open WebUI already has what's needed as of this
year. [PR #21534](https://github.com/open-webui/open-webui/pull/21534)
added native Anthropic `/v1/messages` proxy support
(`ENABLE_ANTHROPIC_API`), and separately Anthropic ships a plain
OpenAI-compatible endpoint that needs only an API key and no middleware.
Either is `standard` risk, registered the same way any other model is.

## Claude Code

[tfriedel/openwebui-claude-code](https://github.com/tfriedel/openwebui-claude-code)
runs the real Claude Code agent loop, via the Claude Agent SDK, as a
selectable model inside Open WebUI. Each chat gets its own persistent
working directory under `WORKDIR_ROOT`, and turns within one chat resume
the same underlying Claude Code session, so file state and prior tool
calls carry forward the way they would in a terminal.

### Authentication: two modes, and they are not interchangeable

- `ANTHROPIC_API_KEY`: ordinary metered billing. No usage restriction; can
  be shared the way any other Novak secret is shared, per
  [cli.md](cli.md)'s "shared" secret category.
- `CLAUDE_CODE_OAUTH_TOKEN`, generated with `claude setup-token`: bills
  against a Pro/Max/Team subscription's Agent SDK credit instead of
  metered usage. When both are configured, OAuth wins, and the pipe's own
  code unsets the API key before invoking the SDK so it cannot be
  overridden back.

**The subscription route is personal, by the terms of service, not by a
technical limitation the pipe imposes.** The pipe's own README states
plainly that OAuth/subscription auth "should only be used personally,
never offered to other users on shared deployments." This is the same
shape of problem the registry already tracks under a different name: one
credential standing in for one person, used by several. That's the
reason Tududi's registry entry carries the note "one token means one
account for everyone." The fix here is the same as there: either the
capability is scoped to one person (see RBAC below), or it authenticates
with the metered API key instead, which carries no such restriction.

**One correction to expectations, since the mechanism changed this
year.** Since 2026-06-15, Claude Code and Agent SDK usage no longer draws
from a subscription's ordinary chat quota. Eligible plans get a separate
monthly Agent SDK credit pool, and usage past that falls back to standard
metered billing. "Using the subscription" here means a bounded credit
pool, not unlimited access riding on the normal chat allowance.

### Where the agent actually executes

This is the part worth reading the source for rather than trusting a
description, so it was read directly rather than taken from the README's
summary.

The default pipe shells out to the `claude` CLI from Open WebUI's own
Python backend process. For Novak that means file and bash access happen
inside the `open-webui` container, which currently has no host bind
mounts and no Docker socket in `docker-compose.yml`, so the blast radius
is that container's own filesystem, not the mini itself. That is
meaningfully contained, but it is containment by omission (nothing was
mounted in) rather than containment by design.

**A sandboxed variant ships in the same repository:**
`claude_agent_pipe_sandboxed.py` isolates the agent inside its own
container with a proxy handling credentials, rather than running inside
Open WebUI's process. Given Novak's stated multi-person intent, this is
the variant to install, not the default. It was not read in as much depth
as the default variant; **VERIFY** its actual isolation boundary (what it
mounts, whether it reaches the Docker socket, whether it can reach the
rest of the Novak network) before trusting it further than "better than
the default."

**`SETTING_SOURCES`, a configuration option the pipe exposes, must stay
off.** It loads persistent settings/context across chats, and the README
states directly that enabling it on a multi-user deployment breaks
per-chat isolation and lets host configuration influence, or run code in,
every user's session. This is not a tuning knob, it's an off switch that
should stay in the off position here.

MCP server passthrough (whether this pipe can hand Claude Code the same
MCP servers already registered in `registry/mcp-servers.yaml`) is
mentioned in the pipe's documentation but not confirmed either way.
**VERIFY** before assuming it, one way or the other.

## Local agent frameworks

Two real candidates, both MIT-licensed, both architecturally different
enough to matter.

| | OpenCode | OpenHands |
|---|---|---|
| Sandbox depth | Client/server; isolation is whatever process runs `opencode serve` | Strongest of the three: spawns a fresh Docker container per task, isolated from the controller |
| Local model support | Yes, confirmed via its Docker Model Runner integration, which proves it speaks a plain OpenAI-compatible endpoint | Yes, via LiteLLM. Ollama confirmed directly; generic OpenAI-compatible endpoints likely, but **VERIFY** against oMLX specifically |
| Own surface | TUI, desktop app, IDE extensions, SDK, not an Open WebUI pipe today | Full web UI: a second interface next to Open WebUI |
| Fits "nothing leaves your machines" | Yes, pointed at oMLX | Yes, pointed at oMLX or an Ollama-compatible endpoint |
| New moving parts | One more service (`opencode serve`) | One more service, plus a container spawned per task |
| Turnkey into Novak's one-interface goal | **No.** Nobody has written an Open WebUI pipe for it yet; using it today means a second surface or writing that pipe | No, same gap, and a bigger surface (a whole second web UI) |

**OpenCode is the closer architectural fit**, on the strength of design
principle 3 (native capability over a maintained wrapper) and principle 9
(single-homed until proven otherwise): it's a thinner addition, and
pointing it at oMLX costs nothing beyond configuration, since oMLX already
serves an OpenAI-compatible endpoint that Docker Model Runner integrations
have already proven this class of tool can consume. **OpenHands is the
stronger choice if isolation depth matters more than surface count**: a
container spawned per task is a materially different security posture
than a long-lived server process, at the cost of a second full web UI
competing with Open WebUI, which cuts against design principle 8
(uniformity across clients) unless that second surface is accepted
deliberately as a separate power-user tool rather than something
household members are expected to use.

**Neither is turnkey today.** The real gap against both is the same one:
nothing currently puts either inside Open WebUI's chat interface the way
the Claude Code pipe does. Using either now means either accepting a
second surface, or building a pipe function for it: real, scoped work
that doesn't exist yet anywhere that was found.

## RBAC: the multi-user question has a native answer

Open WebUI ships real, admin-configurable, per-model access control:
Workspace to Models to the settings icon on any model to visibility, which
can be set to Public, Private, or Restricted to specific groups or users.
This is exactly the mechanism the Claude Code OAuth restriction needs: register
the pipe as a model, set it Restricted, grant only the account whose
subscription is paying for it.

**This is worth naming as a case of design principle 3.** The instinct
when hitting "one credential, must not be shared" is to reach for
something Novak-specific: a wrapper, a check in the reconciler, a new
field in the registry. Open WebUI already solved this, natively, for
exactly this shape of problem, and nothing here needs building. The only
work is configuration: turn the model Private or Restricted, and grant it
to one account.

For a shared capability, where several household members should be able
to use it under their own accountability, the metered
`ANTHROPIC_API_KEY` route has no such restriction and can be granted to a
group the ordinary way. A shared *subscription* credential is the one
combination that doesn't work, by the terms of service, regardless of how
Novak's own access control is configured.

## Risk classification

Every option on this page is `dangerous` under the registry's existing
definition, and that classification should be applied literally when any
of them gets a real entry, not softened because the delivery mechanism (a
pipe function, not an MCP server) is different from what the registry was
originally built to describe.

| Option | Executes where | Registry risk |
|---|---|---|
| Plain chat (native Anthropic proxy or API key) | Nowhere, no tool execution | `standard` |
| Claude Code pipe, default variant | Inside the `open-webui` container's own process | `dangerous` |
| Claude Code pipe, sandboxed variant | A separate container, credential-proxied | `dangerous`, narrower blast radius |
| OpenCode | Wherever `opencode serve` runs | `dangerous` |
| OpenHands | A container spawned per task | `dangerous`, narrowest blast radius of the three agent options |

None of these belong anywhere near the voice pipeline, for the same
reason Tududi and Vikunja were kept off it and more strongly: a misheard
spoken word should never be able to invoke something that writes files or
runs shell commands. That's not a new rule, it's the existing one applied
to a capability with a larger surface than anything it's been applied to
so far.

Whichever option gets adopted first should carry the same fields the
registry already requires above `standard`: `why`, `accepted_by`, and
`accepted_on`, stating specifically what it can do that a person would
regret discovering by surprise, since that's the test the registry's own
comments already set for everything else in it.
