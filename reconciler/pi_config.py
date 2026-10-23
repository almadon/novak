#!/usr/bin/env python3
"""Prints a Pi `models.json` that points Pi at the Novak router (decision #73).

Pi (https://pi.dev) is a terminal coding agent that talks to any OpenAI-style endpoint. The router
is one: this lists its chat roles as a provider named `novak`, with the context window the models
really have (a window that is declared larger than it is makes Pi send prompts the model cuts off).
The key is never written: the file says `$ROUTER_API_KEY` and Pi reads it from the environment.

Usage:  pi_config.py [--url URL] [--context N] [--max-tokens N]
"""
import argparse
import json
import os
import sys

ROLES = [("chat", "Novak chat"), ("deep", "Novak deep")]


def build(url: str, context: int = 8192, max_tokens: int = 2048) -> dict:
    return {
        "$schema": "https://pi.dev/schemas/models.schema.json",
        "providers": {
            "novak": {
                "name": "Novak router",
                "baseUrl": url.rstrip("/"),
                "api": "openai-completions",
                "apiKey": "$ROUTER_API_KEY",
                "models": [{"id": r, "name": n, "contextWindow": context, "maxTokens": max_tokens, "reasoning": False}
                           for r, n in ROLES],
            }
        },
    }


def main(argv=None, env=None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    host = env.get("ROUTER_BIND") or env.get("HOST_NAME") or "localhost"
    ap.add_argument("--url", default=f"http://{host}:{env.get('ROUTER_PORT') or '13402'}/v1")
    ap.add_argument("--context", type=int, default=int(env.get("OLLAMA_CONTEXT_LENGTH") or 8192))
    ap.add_argument("--max-tokens", type=int, default=2048)
    a = ap.parse_args(argv)
    json.dump(build(a.url, a.context, a.max_tokens), sys.stdout, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
