"""Cut long audio into pieces that fit a unit of passive work.

Pieces end at silences where possible, so a word is not cut in half. Pure
functions over the silence list `ffmpeg silencedetect` reports; the ffmpeg
calls themselves are at the bottom.
"""
import re
import subprocess
from pathlib import Path


def plan_chunks(duration: float, silences: list[tuple[float, float]],
                target: float = 60.0, search: float = 15.0) -> list[tuple[float, float]]:
    """Return (start, end) pairs covering [0, duration].

    Each cut goes at the middle of the silence nearest the target within
    +/- `search` seconds, else at the target itself.
    """
    if duration <= target + search:
        return [(0.0, duration)]
    mids = [(s + e) / 2 for s, e in silences]
    out, start = [], 0.0
    while duration - start > target + search:
        goal = start + target
        near = [m for m in mids if abs(m - goal) <= search and m > start + 5]
        cut = min(near, key=lambda m: abs(m - goal)) if near else goal
        out.append((start, cut))
        start = cut
    out.append((start, duration))
    return out


_START = re.compile(r"silence_start: (-?[\d.]+)")
_END = re.compile(r"silence_end: (-?[\d.]+)")
_DUR = re.compile(r"Duration: (\d+):(\d+):([\d.]+)")


def parse_silences(stderr: str) -> list[tuple[float, float]]:
    starts = [float(x) for x in _START.findall(stderr)]
    ends = [float(x) for x in _END.findall(stderr)]
    return [(max(s, 0.0), e) for s, e in zip(starts, ends)]


def probe_duration(stderr: str) -> float:
    m = _DUR.search(stderr)
    if not m:
        raise ValueError("no Duration in ffmpeg output")
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def analyse(path: Path, noise_db=-35, min_silence=0.4) -> tuple[float, list[tuple[float, float]]]:
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
         "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg could not read the audio: {proc.stderr[-300:]}")
    return probe_duration(proc.stderr), parse_silences(proc.stderr)


def extract(path: Path, start: float, end: float, out: Path):
    """Write [start, end) as 16 kHz mono WAV, the format Whisper wants."""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:.3f}",
         "-to", f"{end:.3f}", "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg extract failed: {proc.stderr[-300:]}")
