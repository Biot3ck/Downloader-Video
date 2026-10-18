# Staging image for the Clipora web surface.
#
# This image deliberately does not inherit the local worker image. It contains
# only the web surface, the two shared modules it imports, FFmpeg for MP4/MP3
# conversion, and the hashed runtime lock. Public downloads stay disabled: the
# container is a candidate deployment for the six release blockers, not a
# public launch.
#
# Base digest is the multi-architecture index for python:3.15-slim-trixie.
FROM python:3.15-slim-trixie@sha256:2da676046630d7bf14c6764ae1143dc7fa0377a53f94bf5a642f0b214aca5bce

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY deploy/staging/requirements-runtime.lock /opt/requirements-runtime.lock
RUN python -m pip install --no-cache-dir --no-compile --require-hashes \
        -r /opt/requirements-runtime.lock \
    && rm /opt/requirements-runtime.lock

COPY backend/clipora_v8_web /srv/clipora_v8_web
COPY backend/clipora_v8_browser_real_mp4/job_store.py \
     backend/clipora_v8_browser_real_mp4/artifact_delivery.py \
     /srv/clipora_v8_browser_real_mp4/

WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp TMPDIR=/tmp

# The limiter and the media cache live in the mounted state directory. /data is
# created here so a named volume inherits the unprivileged owner.
RUN mkdir -p /data && chown 10001:10001 /data && chmod 0700 /data

USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2)"]

ENTRYPOINT ["python", "-B", "-m", "uvicorn", "clipora_v8_web.main:app_factory", "--factory"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--no-proxy-headers", \
     "--no-access-log", "--limit-concurrency", "32", "--timeout-keep-alive", "5"]
