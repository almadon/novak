"""Chat completions against the router (any OpenAI-compatible endpoint)."""
import json
import urllib.request


def chat(base_url: str, api_key: str, model: str, messages: list[dict],
         json_mode=False, max_tokens=1500, timeout=900) -> str:
    body = {"model": model, "messages": messages, "max_tokens": max_tokens,
            "temperature": 0.2}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key or 'none'}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    return (data["choices"][0]["message"].get("content") or "").strip()
