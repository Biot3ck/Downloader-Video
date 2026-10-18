# Image staging Clipora

Image ini adalah **kandidat deployment** untuk menutup enam bloker rilis. Bukan
peluncuran publik: `/api/v8/download` tetap `503`, `/healthz` tetap
`ready_for_public_launch: false`, dan route nyata hanya mendaftar bila origin
loopback.

## Kenapa bukan `build_image.py`

`backend/clipora_v8_web/build_image.py` mewarisi image worker lokal
(`clipora-worker:v8-dns`) yang tidak ada di host baru, dan lock-nya hanya berisi
`click`, `h11`, `uvicorn`. Image ini dibangun ulang dari
`python:3.15-slim-trixie` (digest multi-arsitektur), memasang FFmpeg dari Debian,
dan memakai lock runtime ber-hash untuk **linux/arm64 dan linux/amd64**.

Yang ikut ke dalam image:

- `backend/clipora_v8_web/` (termasuk `real_media.py`, jadi deviasi #7 untuk
  sumber ikut tertutup);
- `job_store.py` dan `artifact_delivery.py` dari `clipora_v8_browser_real_mp4`;
- FFmpeg 7.1, `yt-dlp`, `curl_cffi`, `httpx`.

Yang tidak ikut: tes, dokumen internal, halaman developer, dan image worker.

## Build

Dari akar repo:

```sh
docker build -f deploy/staging/Dockerfile -t clipora-web:staging .
```

Lock: `deploy/staging/requirements-runtime.lock`. Setiap paket dipin dan
ber-hash; `pip` menolak wheel yang tidak cocok.

## Uji lokal dengan unduhan nyata

Route nyata hanya aktif untuk origin loopback, jadi jalankan container dengan
origin loopback dan flag nyata:

```sh
docker run --rm -p 127.0.0.1:8090:8080 \
  -e CLIPORA_WEB_ORIGIN=http://127.0.0.1:8090 \
  -e CLIPORA_WEB_STATE=/data \
  -e CLIPORA_REAL_DOWNLOADS=1 \
  -v clipora-test-data:/data \
  clipora-web:staging
```

Lalu:

```sh
curl -s http://127.0.0.1:8090/healthz

curl -s -X POST http://127.0.0.1:8090/api/v8/real/preview \
  -H 'Origin: http://127.0.0.1:8090' -H 'Content-Type: application/json' \
  -d '{"url":"https://www.tiktok.com/@tiktok/video/7694797676306615583","media_kind":"video"}'
```

Hasil yang diharapkan pada 18 Oktober 2026: `platform: tiktok`, `720x1280`,
`formats: ["video","hd","mp3"]`, caption utuh. Unduhan MP3 harus
`content-type: audio/mpeg`, nama `clipora-tiktok-audio.mp3`, dan sekitar 1,2 MB
untuk video 50 detik. Unduhan `hd` menghasilkan MP4 1080x1920.

Catatan: direktori state harus dimiliki UID 10001 dan mode `0700`. Image sudah
membuat `/data` dengan mode itu; volume bernama mewarisinya. Kalau memakai bind
mount, siapkan sendiri:

```sh
install -d -m 0700 -o 10001 -g 10001 ./data
```

## Compose: web di belakang Caddy

`compose.yaml` menjalankan dua service:

- `web`: image di atas, tanpa port publik, `read_only`, `cap_drop: ALL`,
  `no-new-privileges`, batas memori/PID, state di volume `/data`;
- `caddy`: TLS otomatis untuk `CLIPORA_DOMAIN`, meneruskan ke `web:8080`.

Karena Caddy adalah satu-satunya jalur masuk, container web memakai
`--proxy-headers --forwarded-allow-ips=172.28.0.0/16`. Tanpa itu, limiter
melihat semua klien sebagai IP Caddy dan kuota per-klien menjadi kuota global.
Jaringan compose dipatok ke `172.28.0.0/16` supaya allowlist itu tepat.

```sh
cp .env.example .env
# isi CLIPORA_DOMAIN
docker compose up -d --build
```

## Uji ekstraksi nyata di host staging

Instance publik sengaja memakai origin HTTPS, sehingga route nyata tidak
mendaftar. Untuk membuktikan pipeline di host yang sama, jalankan overlay
`real-test` yang hanya bind ke loopback host:

```sh
docker compose -f compose.yaml -f compose.real-test.yaml --profile real-test up -d real-test
```

Dari komputer Anda:

```sh
ssh -N -L 8091:127.0.0.1:8091 ubuntu@<host>
```

Buka `http://127.0.0.1:8091`. Setelah selesai:

```sh
docker compose -f compose.yaml -f compose.real-test.yaml --profile real-test down
```

## Yang belum tertutup

- Gerbang publik dan enam bloker rilis (lihat `backend/clipora_v8_web/docs/RELEASE_SECURITY.md`).
- YouTube: 0/20 dari IP datacenter pada tiga client; jangan dijanjikan publik.
- Batas unduhan, kuota total, dan sustained load baru bisa diuji di host nyata.
