# Reverse proxy config

**Novak does not run a reverse proxy.** These are snippets to add to the
internal proxy you already run on another host.

## What problem this solves

Not public access — that's handled separately (see
[../docs/decisions.md](../docs/decisions.md) #15: public ingress lives on the
VPS, home forwards nothing).

This is about **encryption in transit on the local network**. Worth being
precise about what was and wasn't already covered:

| Path | Before | Why |
|---|---|---|
| Between Tailscale devices | **already encrypted** | Tailscale is WireGuard underneath |
| Across the LAN | **plaintext** | HA → memory, browser → console, anything hitting a published port by IP |

So the tailnet was never the exposure. The LAN was.

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

# Replace <mac-ts-ip> with the Mac's Tailscale address (100.x.y.z).
omlx.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:8080          # VERIFY against OMLX_PORT
}

memory.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:8003          # the MCP endpoint clients register
}

mem0.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:8765          # REST API; Konzol only, never models
}

konzol.novak.example.tld {
	import novak-internal
	reverse_proxy <mac-ts-ip>:3002          # omit if not running the console
}
```

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
          - url: "http://<mac-ts-ip>:8003"
```

Repeat per service. Novak publishes no Docker labels, because the containers
run on a different host from Traefik — label-based discovery won't see them.
The file provider is the right mechanism here.

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
