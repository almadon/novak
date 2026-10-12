# Pinned to the digest python:3.13-slim resolved to on 2026-10-12 (decision #45).
FROM python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# ffmpeg decodes whatever a recorder produces (Ogg Opus, WAV, MP3, M4A) and
# finds the silences the chunker cuts at. PyYAML reads registry/ingest.yaml.
# Application code is mounted, not copied (same as persona/), so a code change
# is a restart, not a rebuild.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pyyaml==6.0.3

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "-m", "novak_ingest", "serve"]
