# Reverse proxy config

**Novak does not run a reverse proxy for the rest of the stack.** These are
snippets to add to the internal proxy you already run on another host.

One exception, added later and narrower: the [portal](#portal-a-single-page-over-open-webui-and-konzol)
runs its own small Caddy instance, but only to gate one static page. It does
not front Open WebUI, Konzol, or anything else this document covers, and
the statement above still holds for all of that.

## What problem this solves

Not public access — that's handled separately (see
[decisions.md](decisions.md) #15: public ingress lives on the
VPS, home forwards nothing).

This is about **encryption in transit on the local network**. Worth being
precise about what was and wasn't already covered:

| Path | Before | Why |
|---|---|---|
| Between Tailscale devices | **already encrypted** | Tailscale is WireGuard underneath |
| Across the LAN | **plaintext** | HA → memory, browser → console, anything hitting a published port by IP |

So the tailnet was never the exposure. The LAN was.

## Which of these may face the internet

**None of them.** This proxy is internal — it exists for TLS on your own
network, not to publish anything. Public ingress is a different proxy, on the
VPS, in front of Open WebUI only (decision #15).

That distinction is the one worth holding onto, because the two look identical
in a config file. A `reverse_proxy` line does not know whether the name in
front of it resolves publicly, and the difference between a private service and
an exposed one is often a single DNS record someone added months earlier.

### What goes wrong, per service

Not a ranking of paranoia — each has a specific failure that follows from what
it is.

| Service | Public? | What actually happens |
|---|---|---|
| **oMLX** (8000) | **No** | An inference API with no rate limiting and no quotas. A stranger with the key gets your GPU; a stranger without one still costs you every connection's worth of work. Worse, it is one endpoint away from your models and your machine's memory ceiling — the way to take this house down is to ask it to think. |
| **Hindsight** (13403, 13404) | **No** | Holds every person's memories. Auth is one shared bearer token: no per-user identity, no rate limit, no lockout. Leak it once and there is no revoking it for one caller. Deletes are permanent, so the damage is not only disclosure. |
| **Konzol** (13401) | **No** | Reconfigures the stack. It writes the registry, and the registry decides what runs. Treat public access to it as equivalent to a shell. |
| **Wyoming** (13406/13405/13407) | **No** | No authentication of any kind, by protocol design. Anything that reaches the port can speak to your microphones' pipeline. |
| **Open WebUI** (13400) | Yes — **via its own public-facing proxy, on a separate host** | The only one built for it: accounts, sessions, its own rate limiting, and it expects strangers to knock. It is public because it earned it, not because it was convenient. |

### The test

Being reachable from the internet is a property a service **earns by being
designed for it**. Concretely, ask of anything you are tempted to expose:

1. Does it authenticate individual callers, or does it have one shared secret?
2. Does it survive someone hammering it — rate limits, quotas, timeouts?
3. If its credential leaked, could you revoke access for one caller without
   breaking every other?
4. Is it maintained closely enough that you will actually apply its security
   updates?

Anything running directly on a service host fails at least the first two. That is not a criticism of
them; they were written for a trusted network, which is exactly where they are.

### If you need it from outside

Use Tailscale. That is the whole reason it is here: the service stays private
and you stop needing a decision about exposure at all. Adding a device to the
tailnet is not a security event in the way opening a port is — you can see who
is on it, and you can take them off.

**Never port-forward directly to a service host**, and be precise about why:
the whole point is that it forwards nothing today, which is what makes it
safe for oMLX to bind `0.0.0.0` and be reachable across the tailnet. Those
two facts are load-bearing together. Add a forward and you have not
"exposed one port" — you have published a rate-limitless inference API,
because the bind was already permissive on the assumption nothing inbound
could arrive.

### If you decide to expose something anyway

That is a legitimate decision, not a forbidden one — but write it down with the
same shape as a risk acceptance in the registry: what it is, why it needs public
reach, what sits in front of it, and who accepted it. A decision recorded is one
someone can revisit; a port quietly forwarded is one nobody remembers making.

## The shape

```
   browser / HA  ──TLS──▶  your internal proxy  ──Tailscale──▶  the service host
                            (other host)         (WireGuard)
```

Both hops are encrypted, and no new infrastructure is added. The last hop
relies on Tailscale rather than TLS, which is fine — WireGuard is not a weaker
guarantee than TLS.

**Requirement:** the proxy host and whichever host runs a given service must
both be on the tailnet, and the proxy should reach it by its **Tailscale**
address, not its LAN
address. Using the LAN address puts the last hop back in plaintext and undoes
the point of the exercise.

## Certificates

Use a **DNS-01** challenge. It proves you own the domain by writing a DNS
record instead of accepting an inbound connection, which is what makes real
certificates possible for names that resolve to a private address behind no
port forwarding.

## Caddy

**Corrected 2026-08-29 for decision #28.** These snippets used to say
`<mac-ts-ip>` throughout, on the assumption there is exactly one host and
it's a Mac. Replace `<engine-host-ts-ip>` / `<core-host-ts-ip>` below with
whichever host actually runs each service — see [engines.md](engines.md)
and decision #28: oMLX and Novak's core services no longer have to be the
same machine, and in this household's own deployment, aren't.

Add to the internal instance (a host separate from whatever runs these
services — see "Which of these may face the internet" above for why):

```caddy
(novak-internal) {
	encode zstd gzip
	header {
		-Server
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
	}
}

# Only if something still needs oMLX directly — most deployments reach it
# through the router instead. Points at whichever host runs oMLX; omit
# entirely if nothing calls it internally. OMLX_PORT is oMLX's own
# default (8000), separate from the clustered block below — it isn't a
# Novak-assigned port.
omlx.novak.example.tld {
	import novak-internal
	reverse_proxy <engine-host-ts-ip>:8000          # OMLX_PORT — see the note below
}

# Ports below match .env.example's clustered default block (decision
# #31, 13400-13409) — real numbers, not placeholders. If this deployment
# set its own values instead, use those; a deployment's real .env is
# always the source of truth over what's written here.
memory.novak.example.tld {
	import novak-internal
	reverse_proxy <core-host-ts-ip>:13403          # HINDSIGHT_PORT: API + MCP at /mcp/<bank>/
}

memory-ui.novak.example.tld {
	import novak-internal
	reverse_proxy <core-host-ts-ip>:13404          # HINDSIGHT_UI_PORT
}

konzol.novak.example.tld {
	import novak-internal
	reverse_proxy <core-host-ts-ip>:13401          # CONSOLE_PORT — omit if not running the console
}
```

**oMLX ships bound to `127.0.0.1`.** On that default nothing off the machine can
reach it, proxy included — containers only manage it because OrbStack forwards
loopback. Change `server.host` in oMLX's own settings before adding the route
above, and check with `novak ports`: the Tailscale column must read `yes`.

**Open WebUI is deliberately absent from the internal proxy.** It's the one
service meant to face the public internet (decision #15) — that's a
*different* proxy, on its own LAN-neighbor host, terminating public
ingress and pointing at whichever host actually runs Open WebUI now. Only
add a route for it *here*, on the internal instance, if you're running a
second copy on the internal network purely for local testing.

Your existing `tlsAutostrap` snippet already handles DNS-01, so these inherit
it from the zone block.

## Traefik

For the planned migration. Same idea, file-provider form:

```yaml
http:
  routers:
    novak-memory:
      rule: "Host(`memory.novak.example.tld`)"
      service: novak-memory
      tls:
        certResolver: dns-01          # VERIFY resolver name in your static config
  services:
    novak-memory:
      loadBalancer:
        servers:
          - url: "http://<core-host-ts-ip>:13403"
```

Repeat per service. Novak publishes no Docker labels, because the containers
run on a different host from Traefik — label-based discovery won't see them.
The file provider is the right mechanism here.

## Giving Home Assistant access to Hindsight

A special case, and the one concrete reason to want a proxy on this network
rather than only for TLS.

**Home Assistant's MCP client authenticates by OAuth only** — the config flow
asks for a Client ID and Secret from Application Credentials, and offers no
field for a bearer token or custom header. **Hindsight authenticates by static
API key** in an `Authorization` header; its shipped tenant extensions are
`Default`, `ApiKey` and `Supabase`, none of them OAuth. Verified: the token is
accepted in a header and nowhere else — as a query parameter it is a 401.

So HA cannot authenticate to Hindsight directly, and the failure is exactly
this:

```
httpx.HTTPStatusError: Client error '401 Unauthorized'
  for url 'http://<core-host-ts-ip>:13403/mcp/household/'
```

The way through is to let the proxy hold the credential and add it per request.
HA then talks to an endpoint that needs no auth from its side, while Hindsight
still refuses anything that reaches it without the key.

```caddy
# Only Home Assistant may use this route — it carries no credential of its own.
@ha remote_ip <ha-tailscale-ip>

memory-ha.novak.example.tld {
	import novak-internal
	handle @ha {
		reverse_proxy <core-host-ts-ip>:13403 {
			header_up Authorization "Bearer {env.HINDSIGHT_API_KEY}"
		}
	}
	respond 403
}
```

Traefik, file provider:

```yaml
http:
  middlewares:
    hindsight-auth:
      headers:
        customRequestHeaders:
          Authorization: "Bearer <key>"     # from the proxy host's secret store
    ha-only:
      ipAllowList:
        sourceRange: ["<ha-tailscale-ip>/32"]
  routers:
    novak-memory-ha:
      rule: "Host(`memory-ha.novak.example.tld`)"
      middlewares: [ha-only, hindsight-auth]
      service: novak-memory
```

**The source restriction is not optional.** This route converts "holds the key"
into "can reach this hostname", so without it anything on the network gets the
household bank uncredentialed. Point Home Assistant at the household bank only
— never a personal one, for the reason in the deploy checklist: a microphone
cannot tell who is speaking.

Note the credential now lives on the proxy host as well as in the service host's
Keychain. That is a second copy to rotate, and it is the cost of the approach.

**Alternatives considered.** Turning Hindsight's tenant auth off would let HA
connect, and would leave the MCP endpoint open to everything that can reach the
port — every bank, read and write. Writing an OAuth tenant extension for
Hindsight is the clean fix and is real work in someone else's codebase. Waiting
for HA's MCP client to accept a token is the other real fix and is not in your
hands.

## What stays plaintext, and why

**The Wyoming voice services** (whisper 13405, piper 13406, openWakeWord
13407). Wyoming is a TCP protocol, not HTTP, and the ESPHome satellites that
speak it can't do TLS to a hostname. Proxying them here would break them.

The honest consequence: someone on your local network could capture voice audio
in transit. That's a smaller exposure than it first sounds — it's the same
network the microphones are already on — but it's real, and nothing in this
directory fixes it.

## Ports on the service host

For this to work, the services must be reachable from the proxy host, so they
bind on the tailnet rather than localhost. That means **anything on your
tailnet can reach them directly**, bypassing the proxy and its TLS.

Tailscale ACLs are the tool for that, not firewall rules on the service host. Worth
setting up if devices you don't fully trust are on the tailnet.

So the tailnet is the real security boundary here — not the proxy, and not the
bind address. The proxy adds TLS for LAN clients; it does not restrict who may
connect. Everything in *Which of these may face the internet* above assumes the
tailnet stays a set of machines you trust, and a phone you lend to a houseguest
is on it until you remove it.

One more thing this directory does not fix: the last hop from the proxy host to whichever host runs
the service in question is WireGuard, not TLS. That is not weaker, but it does mean a service
here never sees a client certificate and cannot tell one tailnet caller from
another. Everything reaching Hindsight presents the same bearer token no matter
who is holding it.

## Portal: a single page over Open WebUI and Konzol

Optional, behind the `portal` compose profile, and unrelated to the rest of
this document's subject: it protects one page, not the stack. Recorded
because two people using it read different names into "reverse proxy" and
it's worth being precise about which one this is.

### What it is, and what it deliberately isn't

A static HTML page (`portal/index.html`) with a tab per app, served by a
Caddy instance that does one other thing: forward-auth every request
against [TinyAuth](https://github.com/tinyauthapp/tinyauth), checked
against Pocket ID's `admins.novak` group — the same group that already
gates the console and, since the `feat/owui-oauth-group-admin` change,
Open WebUI's own admin role. One Pocket ID group now governs three
surfaces.

It does not reverse-proxy Open WebUI or Konzol. Each app keeps its own
port and its own already-working Pocket ID login; the portal's iframes
point straight at those ports, and Caddy's only job is serving the shell
page and gating access to it. This was not a simplicity shortcut. It was
tested directly against the running stack: proxying Open WebUI under a
Caddy subpath (`/app/owui/`) breaks it, because it ships absolute asset
paths (`/static/...`, `/_app/immutable/...`) that resolve against the
proxy's own root rather than the subpath, and Caddy does no URL rewriting
here to fix that up.

Hindsight's own web UI is deliberately not a tab. It has no per-caller
access control beyond the shared tenant API key (see
[security.md](security.md)), and putting it a click away from Open WebUI
makes it too easy to open by habit rather than by intent. Add a tab if
that trade-off is one you want.

### Why TinyAuth

Chosen over [Homepage](https://gethomepage.dev) and
[Organizr](https://organizr.org), the two other real candidates:

- Homepage's iframe widget explicitly does not proxy authentication — each
  embedded tile authenticates on its own, using whatever session the
  browser already has for that app's domain. It's a launcher, not a login
  gate.
- Organizr does genuine iframe tabs, which is closer to what's wanted
  here, but has no native OIDC of its own. Getting one login working would
  mean putting a forward-auth proxy in front of Organizr too, which is
  TinyAuth's whole job, minus a second app with its own local user
  accounts competing with Pocket ID as a fourth identity system.
- Pocket ID's own documentation names TinyAuth as a paired forward-auth
  proxy, and TinyAuth supports Pocket ID's `groups` claim by name.
  OpenID Certified (Basic OP) as of v5.1.0, actively maintained, MIT-scale
  community (8000+ stars) around an AGPL-3.0 core — see
  [credits.md](credits.md) on why running it unmodified keeps that low
  risk.

### What was verified, and what wasn't

Read directly against the running containers, not assumed from
documentation:

- **`TINYAUTH_APPURL` must be a real hostname with a scheme, never an IP.**
  Confirmed directly: TinyAuth refuses to start with "ip addresses not
  allowed" against a bare Tailscale IP, and separately with "invalid url,
  must be in format https(s)://host" against a schemeless hostname.
  `http://mini.local:13408` starts cleanly; `http://100.120.1.110:13408`
  does not start at all. If the portal needs to be reachable from off the
  LAN, use your tailnet's MagicDNS name for the node (visible in
  `tailscale status`), not the IP `novak ports` otherwise reports.
- **Caddy's `templates` directive correctly substitutes `{{env "..."}}`**
  in the served HTML, and Caddyfile's own `{$VAR}` substitution works for
  the listen port — both tested against a real `caddy:2` container before
  being relied on, not assumed from the docs.
- **Open WebUI sends no `X-Frame-Options` or CSP `frame-ancestors` header**
  today, checked directly with `curl -I` against the running container,
  so nothing currently blocks the iframe approach. It does have code
  capable of setting `X-Frame-Options` (opt-in via an environment
  variable, unset here) — if header hardening is ever turned on, keep it
  at `SAMEORIGIN` or leave it unset, never `DENY`, or the portal breaks.
- **Not verified: the actual OAuth-group restriction against a live
  Pocket ID login.** The OIDC connection and `TINYAUTH_APPURL` validation
  were tested directly; whether `TINYAUTH_APPS_PORTAL_OAUTH_GROUPS` and
  `TINYAUTH_APPS_PORTAL_CONFIG_DOMAIN` actually restrict access the way
  the flag names imply was not, since that needs a real round trip against
  a live Pocket ID instance this environment doesn't have. Confirm with an
  account **not** in `admins.novak` and expect it refused before trusting
  this as a real boundary, not just a configured one.

### Setting it up

1. Register a fourth Pocket ID OIDC client (console, Open WebUI, and now
   this each need their own — the redirect URI differs every time), with
   the `groups` scope.
2. Fetch that Pocket ID instance's `/.well-known/openid-configuration` and
   copy `authorization_endpoint`, `token_endpoint`, and `userinfo_endpoint`
   verbatim into `TINYAUTH_OIDC_AUTH_URL`, `_TOKEN_URL`, `_USERINFO_URL`.
   TinyAuth does not do discovery-document lookup the way Open WebUI and
   the console's OIDC libraries do; these three must be spelled out.
3. Set `PORTAL_APPURL` to a real hostname with scheme — see the VERIFY
   above before picking one.
4. `novak secret set TINYAUTH_OIDC_CLIENT_SECRET`, `novak up`.
