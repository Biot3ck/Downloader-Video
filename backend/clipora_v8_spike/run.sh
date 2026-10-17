#!/usr/bin/env bash
# Jalankan spike Fase 0.5 di container Linux (Docker Desktop / Colima / Podman).
#
# PENTING: container di mesin lokal tetap keluar lewat IP rumah Anda. Hasil dari sini
# hanya sah untuk memvalidasi toolchain, BUKAN untuk menilai blokir IP datacenter.
# Untuk keputusan Fase 0.5, jalankan vps_bootstrap.sh di VPS, atau workflow spike.yml
# di GitHub Actions.
#
# Pakai:
#   ./run.sh              # bangun image lalu jalankan spike
#   ./run.sh --egress     # hanya laporkan IP keluar container
#   YT_DLP_VERSION=2026.09.01 ./run.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${IMAGE:-clipora-spike:local}"
YT_DLP_VERSION="${YT_DLP_VERSION:-2026.08.19}"
OUT_DIR="${OUT_DIR:-$HERE/hasil}"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker tidak ditemukan. Pasang Docker Desktop, Colima, atau Podman." >&2
    exit 1
fi

echo "== Membangun image $IMAGE (yt-dlp $YT_DLP_VERSION) =="
docker build \
    --build-arg "YT_DLP_VERSION=$YT_DLP_VERSION" \
    -t "$IMAGE" \
    "$HERE"

mkdir -p "$OUT_DIR"

if [[ "${1:-}" == "--egress" ]]; then
    echo "== IP keluar container =="
    docker run --rm "$IMAGE" --egress-only
    exit $?
fi

if ! grep -qE '^https?://' "$HERE/urls.txt"; then
    echo "urls.txt belum berisi URL sungguhan. Isi dulu, lalu jalankan lagi." >&2
    echo "Berkas: $HERE/urls.txt" >&2
    exit 1
fi

echo "== IP keluar container =="
docker run --rm "$IMAGE" --egress-only || {
    echo "Container tidak punya akses internet. Periksa Docker networking." >&2
    exit 1
}

echo "== Menjalankan spike =="
docker run --rm \
    -v "$HERE/urls.txt:/srv/clipora_v8_spike/urls.txt:ro" \
    -v "$OUT_DIR:/out" \
    "$IMAGE" \
    --urls /srv/clipora_v8_spike/urls.txt \
    --out /out/hasil-spike.csv \
    "$@"

echo
echo "Hasil ada di: $OUT_DIR"
