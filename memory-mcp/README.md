# memory-mcp

An MCP front end for the self-hosted Mem0 server, with per-user scoping.

## Why this exists

Mem0's self-hosted server is REST-only. Novak's architecture depends on memory
being reachable over MCP — Home Assistant's MCP integration and Open WebUI's
tool registration both need it, and without MCP, memory silently drops out of
the voice pipeline. The deprecated OpenMemory server provided MCP; its
replacement does not.

Community mem0 MCP wrappers exist, but they are built for single-user coding
agents. The thing that matters most here — deciding *whose* memories a request
may touch — is the one piece that should not be delegated to a third party. So
this is first-party and deliberately small.

## Trust model

**The caller does not choose the user.** A client presents a bearer token; the
shim maps that token to a `user_id` and injects it into every Mem0 call. There
is no tool parameter, header, or URL path that lets a caller name a different
user. This matters because the LAN includes untrusted devices (see
[../docs/security.md](../docs/security.md), Rule 4) and because a model can be
talked into passing whatever a prompt-injected document tells it to
(Rule 3) — if `user_id` were a tool argument, injected text could read another
person's memories.

Consequences of that choice:

- Every client needs its own token. One token per (person, client) pair is the
  intended granularity — revoking Open WebUI access for one person shouldn't
  revoke their HA access.
- `MEMORY_DEFAULT_USER` is how clients that cannot send an Authorization header
  (Home Assistant) get an identity. It is **off unless explicitly set**, and
  when set the shim warns at startup, because it converts "no token" from an
  error into a silent identity assignment. Set it to a shared household
  identity, never to a real person's `sub` — see the client compatibility
  section below.
- With neither a valid token nor a default, the shim fails closed.

The console does **not** go through this shim. It authenticates users via
Pocket ID and calls the Mem0 REST API directly server-side with an admin key.
This shim is for model clients only.

## Configuration

| Variable | Required | Meaning |
|---|---|---|
| `MEM0_URL` | yes | Base URL of the Mem0 self-hosted server |
| `MEM0_API_KEY` | yes | Server API key, sent as `X-API-Key` |
| `MEMORY_TOKEN_MAP` | yes* | JSON object: `{"<bearer-token>": "<user_id>"}` |
| `MEMORY_DEFAULT_USER` | no | Fallback `user_id` when no token is presented |
| `PORT` | no | Listen port (default 8000) |

\* Not required if `MEMORY_DEFAULT_USER` is set, but see the warning above.

Both `MEM0_API_KEY` and `MEMORY_TOKEN_MAP` are secrets — source them from
Keychain via `scripts/up.sh`, never from `.env` in git.

`user_id` should be the Pocket ID subject (`sub`), so memory, the console, and
Open WebUI all key off one identity.

## Tools

| Tool | Effect |
|---|---|
| `search_memories` | Semantic search within the caller's memories |
| `list_memories` | List the caller's memories |
| `add_memory` | Store a new memory for the caller |
| `delete_memory` | Delete one of the caller's memories by id |

`delete_memory` is the only destructive tool. It verifies the target memory
belongs to the caller before deleting — Mem0's delete endpoint does not
itself enforce ownership, so skipping that check would allow deleting any
memory by guessing an id.

## Client compatibility — READ THIS FIRST

| Client | Auth it can send | Works with this shim today |
|---|---|---|
| Open WebUI | custom headers | ✅ bearer token |
| Console | n/a — calls Mem0 REST directly | ✅ |
| Home Assistant | **OAuth only** | ❌ **no** |

Home Assistant's MCP *client* integration (`mcp`) accepts OAuth Client ID /
Client Secret and nothing else — no bearer token, no custom header. It is also
a **single shared integration instance**, not a per-user connection.

Do not confuse this with HA's MCP *Server* integration (`mcp_server`), which is
the opposite direction (HA exposing its own tools outward, authenticated with a
long-lived access token). The long-lived-token and IndieAuth documentation
belongs to that one and does not apply here.

### The identity problem is worse than the auth problem

Even with working auth, HA has no per-user identity to send. A voice satellite
does not know who is speaking, and the MCP connection belongs to the
integration rather than to a person. So "Alice's memories in Alice's voice
conversation" is not something HA can express today through this interface.

### Decision: shared voice memory

Voice gets **one shared household identity**. Per-user memory exists in Open
WebUI and the console, which can authenticate properly; voice does not pretend
to distinguish people it cannot actually tell apart.

Mechanically that means `MEMORY_DEFAULT_USER` is set to a household identity
and HA connects unauthenticated. So the two modes coexist:

- request **with** a valid bearer token → that user's memories (Open WebUI)
- request **without** a token → the household identity (HA)

**The security consequence, stated plainly:** with `MEMORY_DEFAULT_USER` set,
anything that can reach this port reads and writes household memory without
authenticating. That is tolerable only because household memory is shared by
definition, and only on a Tailscale-only path — do not publish this port to a
flat LAN carrying IoT devices (see [../docs/security.md](../docs/security.md),
Rule 4). Per-user memories stay protected: they require a token, and no
unauthenticated caller can reach them.

Revisit if HA gains speaker identification, or implement OAuth here if HA
should authenticate as itself. Note that OAuth would fix authentication but not
the who-is-speaking problem — it identifies *Home Assistant*, not a person.

## Status — UNVERIFIED

Written against Mem0's documented REST surface without a running server to test
against. Before trusting it:

1. Confirm the endpoint paths and response shapes in `src/mem0.ts` against your
   actual Mem0 version — these were taken from documentation, not observed
   traffic.
2. Verify Open WebUI and Home Assistant can both send an `Authorization` header
   to an MCP server. If Home Assistant cannot, that is the case
   `MEMORY_DEFAULT_USER` is for, and it means HA is effectively single-user
   until that changes.
3. Test that `delete_memory` refuses a memory belonging to another user.
