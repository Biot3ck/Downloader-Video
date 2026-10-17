# Lingkungan Linux untuk spike Fase 0.5. Bukan image produksi.
#
# Sengaja minimal: hanya Python, CA certificate, dan yt-dlp. Tidak ada FFmpeg karena
# spike hanya membaca metadata, tidak mengunduh media.
#
# Versi yt-dlp dipin supaya hasil bisa dibandingkan antar jalannya spike. Naikkan
# versi secara sadar, lalu catat di laporan.

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

ARG YT_DLP_VERSION=2026.08.19
RUN python -m pip install --no-cache-dir "yt-dlp==${YT_DLP_VERSION}"

WORKDIR /srv
COPY __init__.py spike.py /srv/clipora_v8_spike/
COPY urls.txt /srv/clipora_v8_spike/urls.txt

RUN useradd --system --uid 10001 spike \
 && mkdir -p /out \
 && chown -R 10001:10001 /srv /out

USER 10001

ENTRYPOINT ["python", "-B", "-m", "clipora_v8_spike.spike"]
CMD ["--help"]
