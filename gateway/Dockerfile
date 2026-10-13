# Pinned to the digest python:3.13-slim resolved to on 2026-10-12 (decision #45).
FROM python@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f

# PyJWT and cryptography check Pocket ID tokens; PyYAML reads the registry.
# Application code is mounted, not copied, so a code change is a restart.
RUN pip install --no-cache-dir pyyaml==6.0.3 pyjwt==2.15.1 cryptography==50.0.2

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
CMD ["python", "-m", "novak_gateway", "serve"]
