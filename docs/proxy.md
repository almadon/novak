# Reverse proxy config

**Novak does not run a reverse proxy.** These are snippets to add to the
internal proxy you already run on another host.

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
| **Hindsight** (8888, 9999) | **No** | Holds every person's memories. Auth is one shared bearer token: no per-user identity, no rate limit, no lockout. Leak it once and there is no revoking it for one caller. Deletes are permanent, so the damage is not only disclosure. |
| **Konzol** (3002) | **No** | Reconfigures the stack. It writes the registry, and the registry decides what runs. Treat public access to it as equivalent to a shell. |
| **Wyoming** (10200/10300/10400) | **No** | No authentication of any kind, by protocol design. Anything that reaches the port can speak to your microphones' pipeline. |
| **Open WebUI** (3000) | Yes — **on the VPS** | The only one built for it: accounts, sessions, its own rate limiting, and it expects strangers to knock. It is public because it earned it, not because it was convenient. |

### The test

Being reachable from the internet is a property a service **earns by being
designed for it**. Concretely, ask of anything you are tempted to expose:

1. Does it authenticate individual callers, or does it have one shared secret?
2. Does it survive someone hammering it — rate limits, quotas, timeouts?
3. If its credential leaked, could you revoke access for one caller without
   breaking every other?
4. Is it maintained closely enough that you will actually apply its security
   updates?

Anything on the Mac fails at least the first two. That is not a criticism of
them; they were written for a trusted network, which is exactly where they are.

### If you need it from outside

Use Tailscale. That is the whole reason it is here: the service stays private
and you stop needing a decision about exposure at all. Adding a device to the
tailnet is not a security event in the way opening a port is — you can see who
is on it, and you can take them off.

**Never port-forward to the Mac**, and be precise about why: the mini forwards
nothing today, which is what makes it safe for oMLX to bind `0.0.0.0` and be
reachable across the tailnet. Those two facts are load-bearing together. Add a
forward and you have not "exposed one port" — you have published a rate-limitless
inference API, because the bind was already permissive on the assumption nothing
inbound could arrive.

### If you decide to expose something anyway

That is a legitimate decision, not a forbidden one — but write it down with the
same shape as a risk acceptance in the registry: what it is, why it needs public
reach, what sits in front of it, and who accepted it. A decision recorded is one
someone can revisit; a port quietly forwarded is one nobody remembers making.

## The shape

```
   browser / HA  ──TLS──▶  your internal proxy  ──Tailscale──▶  the Mac
                            (other host)         (WireGuard)
```

Both hops are encrypted, and no new infrastructure is added. The last hop
relies on Tailscale rather than TLS, which is fine — WireGuard is not a weaker
guarantee than TLS.

**Requirement:** the proxy host and the Mac must both be on the tailnet, and
the proxy should reach the Mac by its **Tailscale** address, not its LAN
address. Using the LAN address puts the last hop back in plaintext and undoes
the point of the exercise.

## Certificates

Use a **DNS-01** challenge. It proves you own the domain by writing a DNS
record instead of accepting an inbound connection, which is what makes real
certificates possible for names that resolve to a private address behind no
port forwarding.

## Caddy

Current setup. Add to the internal instance:

```caddy
(novak-internal) {
	encode zstd gzip
	header {
		-Server
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options "nosniff"
	}
}

# Replace <mac-ts-ip> with the Mac's Tailscale address (100.x.y.z), or its
# MagicDNS name.
omlx.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:8000          # OMLX_PORT — see the note below
}

memory.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:8888          # Hindsight: API + MCP at /mcp/<bank>/
}

memory-ui.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:9999          # Hindsight's web UI
}

konzol.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:3002          # omit if not running the console
}
```

**oMLX ships bound to `127.0.0.1`.** On that default nothing off the machine can
reach it, proxy included — containers only manage it because OrbStack forwards
loopback. Change `server.host` in oMLX's own settings before adding the route
above, and check with `novak ports`: the Tailscale column must read `yes`.

**Open WebUI (3000) is deliberately absent.** It runs on the VPS, where public
ingress already terminates TLS for it — see decisions #15. Only add a route
here if you are running it on the Mac for local testing.

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
          - url: "http://<mac-ts-ip>:8888"
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
  for url 'http://<mac>:8888/mcp/household/'
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
		reverse_proxy <mac-ts-ip>:8888 {
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

Note the credential now lives on the proxy host as well as in the Mac's
Keychain. That is a second copy to rotate, and it is the cost of the approach.

**Alternatives considered.** Turning Hindsight's tenant auth off would let HA
connect, and would leave the MCP endpoint open to everything that can reach the
port — every bank, read and write. Writing an OAuth tenant extension for
Hindsight is the clean fix and is real work in someone else's codebase. Waiting
for HA's MCP client to accept a token is the other real fix and is not in your
hands.

## What stays plaintext, and why

**The Wyoming voice services** (whisper 10300, piper 10200, openWakeWord
10400). Wyoming is a TCP protocol, not HTTP, and the ESPHome satellites that
speak it can't do TLS to a hostname. Proxying them here would break them.

The honest consequence: someone on your local network could capture voice audio
in transit. That's a smaller exposure than it first sounds — it's the same
network the microphones are already on — but it's real, and nothing in this
directory fixes it.

## Ports on the Mac

For this to work, the services must be reachable from the proxy host, so they
bind on the tailnet rather than localhost. That means **anything on your
tailnet can reach them directly**, bypassing the proxy and its TLS.

Tailscale ACLs are the tool for that, not firewall rules on the Mac. Worth
setting up if devices you don't fully trust are on the tailnet.

So the tailnet is the real security boundary here — not the proxy, and not the
bind address. The proxy adds TLS for LAN clients; it does not restrict who may
connect. Everything in *Which of these may face the internet* above assumes the
tailnet stays a set of machines you trust, and a phone you lend to a houseguest
is on it until you remove it.

One more thing this directory does not fix: the last hop from the proxy host to
the Mac is WireGuard, not TLS. That is not weaker, but it does mean a service
here never sees a client certificate and cannot tell one tailnet caller from
another. Everything reaching Hindsight presents the same bearer token no matter
who is holding it.
