# Pinned to the digest python:3.13-slim resolved to on 2026-10-12 (decision #45).
FROM python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# ffmpeg decodes whatever a recorder produces (Ogg Opus, WAV, MP3, M4A) and
# finds the silences the chunker cuts at; tzdata makes TZ mean something. PyYAML
# reads registry/ingest.yaml. Application code is mounted, not copied (same as
# persona/), so a code change is a restart, not a rebuild.
#
# The apt and pip caches are BuildKit cache mounts: they persist on the builder
# between builds, so a rebuild (a changed pin, a new line here) does not download
# ffmpeg's dependencies again. Debian's image deletes downloaded packages after
# every install (docker-clean), which defeats a cache, so that is switched off
# here. Nothing in the cache ends up in the image.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
 && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache \
 && apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tzdata
RUN --mount=type=cache,target=/root/.cache/pip pip install pyyaml==6.0.3

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "-m", "novak_ingest", "serve"]
