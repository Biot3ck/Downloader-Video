#!/usr/bin/env bash
# Jalankan spike Fase 0.5 di VPS Linux lewat SSH, lalu tarik hasilnya kembali.
#
# Ini jalur yang SAH untuk keputusan Fase 0.5, karena yang diuji adalah perilaku
# platform terhadap IP datacenter — bukan IP rumah.
#
# Pakai:
#   ./vps_spike.sh root@203.0.113.10
#   ./vps_spike.sh ubuntu@203.0.113.10 --key ~/.ssh/id_ed25519
#   ./vps_spike.sh ubuntu@host --recheck      # uji ulang 24 jam kemudian
#
# Prasyarat di VPS: Debian 12 / Ubuntu 22.04+, akses SSH, python3 (tanpa venv pun bisa
# bila python3-venv terpasang; skrip memasangnya bila perlu dan punya sudo).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REMOTE_DIR="${REMOTE_DIR:-/tmp/clipora-spike}"
YT_DLP_VERSION="${YT_DLP_VERSION:-2026.08.19}"
OUT_DIR="${OUT_DIR:-$HERE/hasil}"

HOST=""
SSH_KEY=""
RECHECK=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --key) SSH_KEY="$2"; shift 2 ;;
        --recheck) RECHECK=1; shift ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*) echo "opsi tidak dikenal: $1" >&2; exit 1 ;;
        *) HOST="$1"; shift ;;
    esac
done

if [[ -z "$HOST" ]]; then
    echo "pakai: $0 user@host [--key path] [--recheck]" >&2
    exit 1
fi

for cmd in ssh rsync; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "$cmd tidak ditemukan" >&2; exit 1; }
done

SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15)
RSYNC_SSH="ssh ${SSH_OPTS[*]}"
if [[ -n "$SSH_KEY" ]]; then
    SSH_OPTS+=(-i "$SSH_KEY")
    RSYNC_SSH="ssh ${SSH_OPTS[*]}"
fi

if ! grep -qE '^https?://' "$HERE/urls.txt"; then
    echo "urls.txt belum berisi URL sungguhan. Isi dulu: $HERE/urls.txt" >&2
    exit 1
fi

# Periksa komposisi daftar di Mac sebelum menyentuh VPS: sampel yang terlalu kecil
# menghasilkan angka yang terlihat pasti padahal tidak berarti.
if command -v python3 >/dev/null 2>&1; then
    ( cd "$HERE/.." && python3 -B -m clipora_v8_spike.spike \
        --urls clipora_v8_spike/urls.txt --audit-only ) \
        || echo "Peringatan: daftar URL belum lengkap. Spike tetap dijalankan, tetapi hasilnya lemah." >&2
fi

echo "== 1/4 Cek koneksi ke $HOST =="
ssh "${SSH_OPTS[@]}" "$HOST" 'echo "terhubung: $(uname -srm)"; echo "ip: $(curl -s --max-time 6 https://api.ipify.org || echo tidak-terdeteksi)"'

echo "== 2/4 Menyalin alat spike =="
rsync -az --delete -e "$RSYNC_SSH" "$HERE/" "$HOST:$REMOTE_DIR/"

echo "== 3/4 Menyiapkan Python dan yt-dlp di VPS =="
ssh "${SSH_OPTS[@]}" "$HOST" bash -s <<REMOTE
set -euo pipefail
cd "$REMOTE_DIR"

if ! python3 -c 'import venv' >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        SUDO=""; [ "\$(id -u)" -ne 0 ] && SUDO="sudo"
        \$SUDO apt-get update -qq
        \$SUDO apt-get install -y -qq python3-venv ca-certificates curl >/dev/null
    else
        echo "python3-venv tidak tersedia dan apt-get tidak ada. Pasang manual." >&2
        exit 1
    fi
fi

rm -rf .venv
python3 -m venv .venv
./.venv/bin/pip install --quiet --disable-pip-version-check "yt-dlp==$YT_DLP_VERSION"
./.venv/bin/python -c 'import yt_dlp; print("yt-dlp", yt_dlp.version.__version__)'
REMOTE

echo "== 4/4 Menjalankan spike =="
RECHECK_ARG=""
if [[ "$RECHECK" -eq 1 ]]; then
    if [[ -f "$OUT_DIR/hasil-spike.csv" ]]; then
        rsync -az -e "$RSYNC_SSH" "$OUT_DIR/hasil-spike.csv" "$HOST:$REMOTE_DIR/hasil-sebelumnya.csv"
        RECHECK_ARG="--recheck hasil-sebelumnya.csv"
    else
        echo "Peringatan: --recheck diminta tetapi hasil sebelumnya tidak ada. Jalan penuh." >&2
    fi
fi

ssh "${SSH_OPTS[@]}" "$HOST" "cd $REMOTE_DIR && ./.venv/bin/python -B -m clipora_v8_spike.spike --urls urls.txt --out hasil-spike.csv $RECHECK_ARG"

mkdir -p "$OUT_DIR"
rsync -az -e "$RSYNC_SSH" \
    "$HOST:$REMOTE_DIR/hasil-spike.csv" \
    "$HOST:$REMOTE_DIR/hasil-spike.md" \
    "$OUT_DIR/"

echo
echo "Hasil ditarik ke: $OUT_DIR"
echo "Baca: $OUT_DIR/hasil-spike.md"
