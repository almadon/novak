"""Speech-to-text over HTTP. whisper.cpp's server by default, or anything
that takes a multipart `file` and returns segments (OpenAI-style)."""
import json
import uuid
import urllib.request
from pathlib import Path


def multipart(fields: dict, file_field: str, filename: str, data: bytes):
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
         f'filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n').encode()
        + data + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def transcribe(url: str, path: str, wav: Path, language="auto", extra=None,
               timeout=1800) -> list[dict]:
    """Returns [{start, end, text}] in seconds relative to the file sent."""
    fields = {"response_format": "verbose_json", "temperature": "0.0",
              "language": language, **(extra or {})}
    body, ctype = multipart(fields, "file", wav.name, wav.read_bytes())
    req = urllib.request.Request(url.rstrip("/") + path, data=body,
                                 headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        payload = json.load(r)
    if "error" in payload:
        raise RuntimeError(f"stt error: {payload['error']}")
    segs = payload.get("segments")
    if segs is None:  # plain {"text": ...}
        text = (payload.get("text") or "").strip()
        return [{"start": 0.0, "end": 0.0, "text": text}] if text else []
    out = []
    for s in segs:
        text = (s.get("text") or "").strip()
        if text:
            out.append({"start": float(s.get("start", 0)), "end": float(s.get("end", 0)),
                        "text": text})
    return out
