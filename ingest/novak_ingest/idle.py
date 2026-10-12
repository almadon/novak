"""The backseat rule: passive work runs only when nobody is using the models.

Chat in Open WebUI and voice from Home Assistant are active; transcription and
summarising are passive and wait. The probe asks Ollama which models are loaded
and when each was last used. With a keep-alive of K seconds, a model's
`expires_at` is its last use plus K, so the last use is `expires_at - K`.

This service's own calls refresh `expires_at` too, so they are subtracted:
without that, finishing one summary would make the box look busy for the whole
quiet window and the next one would never start.

VERIFY on a live Ollama that `expires_at` moves at the end of a request as
assumed here; `python -m novak_ingest idle` prints what the probe sees.
"""
import json
import time
import urllib.request
from datetime import datetime

OWN_SLACK_S = 5.0


def parse_ts(value: str) -> float:
    """Ollama sends RFC 3339 with nanoseconds and an offset; trim to microseconds."""
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    head, _, tail = value.partition(".")
    if tail:
        frac = ""
        rest = ""
        for i, ch in enumerate(tail):
            if ch.isdigit():
                frac += ch
            else:
                rest = tail[i:]
                break
        value = f"{head}.{frac[:6].ljust(6, '0')}{rest}"
    return datetime.fromisoformat(value).timestamp()


class IdleGate:
    def __init__(self, probe, quiet_s=180.0, poll_s=15.0, clock=time.time, sleep=time.sleep):
        self.probe, self.quiet_s, self.poll_s = probe, quiet_s, poll_s
        self.clock, self.sleep = clock, sleep
        self.own_last = 0.0

    def note_own_activity(self):
        self.own_last = self.clock()

    def last_foreign_use(self):
        """Newest model use that was not ours, or None when nothing was used."""
        times = [t for t in self.probe() if t > self.own_last + OWN_SLACK_S]
        return max(times) if times else None

    def is_idle(self) -> bool:
        last = self.last_foreign_use()
        return last is None or self.clock() - last >= self.quiet_s

    def wait(self, should_stop=lambda: False) -> bool:
        """Block until idle. Returns False if asked to stop first."""
        while not should_stop():
            try:
                if self.is_idle():
                    return True
            except Exception:
                pass  # a probe that cannot be reached means we cannot prove idle
            self.sleep(self.poll_s)
        return False


def ollama_probe(base_url: str, keep_alive_s: float, timeout=5):
    def probe() -> list[float]:
        with urllib.request.urlopen(base_url.rstrip("/") + "/api/ps", timeout=timeout) as r:
            models = json.load(r).get("models", [])
        return [parse_ts(m["expires_at"]) - keep_alive_s for m in models if m.get("expires_at")]

    return probe


def always_idle_probe():
    return lambda: []
