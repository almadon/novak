"""Settings. Infrastructure comes from the environment (compose sets it);
behaviour comes from registry/ingest.yaml, which names secrets, never holds them."""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS = {
    "idle": {"probe": "ollama", "quiet_s": 180, "poll_s": 15},
    "stt": {"path": "/inference", "language": "auto", "chunk_s": 60, "search_s": 15,
            "extra": {}},
    "summary": {"role": "chat", "window_words": 2500},
    "inbox_poll_s": 10,
    "max_attempts": 3,
    "sinks": [],
}
SINK_KINDS = ("note", "memory", "task")


def unplaceholder(value: str) -> str:
    """A secret still holding its .env.example placeholder is not a secret."""
    return "" if value in ("set-in-keychain", "EDIT-ME", "changeme") else value


def parse_duration(value: str, default: float) -> float:
    """Ollama keep-alive spellings: 300, 5m, 24h, 1h30m, -1 (never unload)."""
    import re
    value = (value or "").strip()
    if not value:
        return default
    if value.startswith("-"):
        return float("inf")
    if re.fullmatch(r"\d+(\.\d+)?", value):
        return float(value)
    parts = re.findall(r"(\d+(?:\.\d+)?)([smh])", value)
    if not parts or "".join(a + b for a, b in parts) != value:
        raise ConfigError(f"cannot read duration {value!r}")
    return sum(float(n) * {"s": 1, "m": 60, "h": 3600}[u] for n, u in parts)


class ConfigError(ValueError):
    pass


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def validate(cfg: dict) -> dict:
    if cfg["idle"]["probe"] not in ("ollama", "none"):
        raise ConfigError("idle.probe must be 'ollama' or 'none'")
    if cfg["idle"]["quiet_s"] < 0 or cfg["stt"]["chunk_s"] < 10:
        raise ConfigError("idle.quiet_s must be >= 0 and stt.chunk_s >= 10")
    seen = set()
    for s in cfg["sinks"]:
        name = s.get("name")
        if not name or name in seen:
            raise ConfigError(f"sink names must be present and unique (got {name!r})")
        seen.add(name)
        if s.get("kind") not in SINK_KINDS:
            raise ConfigError(f"sink {name}: kind must be one of {SINK_KINDS}")
        if not s.get("tool") or not isinstance(s.get("mcp"), dict):
            raise ConfigError(f"sink {name}: needs 'tool' and an 'mcp' block")
        if not (s["mcp"].get("url") or s["mcp"].get("url_env")):
            raise ConfigError(f"sink {name}: mcp needs 'url' or 'url_env'")
    return cfg


def load_yaml(path: str | None) -> dict:
    raw = {}
    if path and Path(path).exists():
        raw = (yaml.safe_load(Path(path).read_text()) or {}).get("ingest") or {}
    return validate(_merge(DEFAULTS, raw))


@dataclass
class Settings:
    data: Path
    token: str
    public_url: str
    stt_url: str
    llm_base_url: str
    llm_api_key: str
    ollama_url: str
    keep_alive_s: float
    ha_url: str
    ha_token: str
    ha_target: str
    ticker_category: str
    max_upload_mb: int
    cfg: dict = field(default_factory=dict)

    @classmethod
    def from_env(cls, env=os.environ):
        e = env.get
        return cls(
            data=Path(e("INGEST_DATA", "/data")),
            token=e("INGEST_TOKEN", ""),
            public_url=e("INGEST_PUBLIC_URL", "http://localhost:13409").rstrip("/"),
            stt_url=e("INGEST_STT_URL", "http://stt:8080"),
            llm_base_url=e("INGEST_LLM_BASE_URL", "http://router:4000/v1"),
            llm_api_key=e("INGEST_LLM_API_KEY", "none"),
            ollama_url=e("INGEST_OLLAMA_URL", "http://ollama:11434"),
            # Must match Ollama's OLLAMA_KEEP_ALIVE (the idle probe reads it back
            # from expires_at). Ollama's own default is 5 minutes.
            keep_alive_s=parse_duration(
                e("INGEST_KEEP_ALIVE") or e("OLLAMA_KEEP_ALIVE", ""), 300.0),
            ha_url=e("INGEST_HA_URL", ""),
            ha_token=unplaceholder(e("INGEST_HA_TOKEN", "")),
            ha_target=e("INGEST_HA_NOTIFY_TARGET", ""),
            ticker_category=e("INGEST_TICKER_CATEGORY", "") or "general",
            max_upload_mb=int(e("INGEST_MAX_UPLOAD_MB", "512")),
            cfg=load_yaml(e("INGEST_CONFIG", "/registry/ingest.yaml")),
        )
