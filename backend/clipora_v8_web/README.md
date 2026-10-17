# Clipora v8 — frontend produk

Frontend memakai HTML/CSS/JavaScript dan FastAPI yang sudah ada. Identitas Clipora ungu/terang dipertahankan; navigasi menyediakan Video Downloader, Photo Downloader, Audio Downloader dan History. Video/foto memakai pengenalan URL yang ada. Audio dan History belum tersedia dan ditampilkan dengan jujur. Tidak ada hasil unduhan palsu atau unduhan platform publik yang diaktifkan.

Lihat [UI_RESTRUCTURE.md](UI_RESTRUCTURE.md) untuk audit, branch/checkpoint, file yang berubah, pengujian responsif dan keterbatasan.

Halaman Video juga menyediakan preferensi Video, Video HD dan MP3 dengan status belum tersedia. Check link tetap hanya mengenali platform; tidak memulai download/konversi atau iklan. Rancangan kualitas asli dan rewarded ads ada di [VIDEO_FORMATS.md](VIDEO_FORMATS.md).

## Preview lokal

Dari backend:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090
```

Produk tersedia pada http://127.0.0.1:8090. Untuk utilitas developer offline gunakan --offline-workflow dan --state /absolute/private/state; buka /dev secara langsung. Halaman utama tetap bersih dari semua fixture. /dev hanya tersedia pada mode offline eksplisit + HTTP loopback, tidak pada default atau HTTPS. Halaman developer memakai API job/ownership yang sudah ada.

Kode preview file perangkat untuk calon Tools disimpan pada tools_archive/device-preview dan tidak disajikan HTTP. Tidak ada input file pada halaman produk.

## Batas keamanan

Hasil pemeriksaan dan blocker persetujuan publik terbaru: [RELEASE_SECURITY.md](RELEASE_SECURITY.md). State limiter wajib path kanonis tanpa symlink, direktori milik UID proses 0700 dan database regular privat 0600; konfigurasi yang tidak aman ditolak tanpa diperbaiki otomatis. Launcher lokal sudah memakai path kanonis.

Host/Origin persis, POST 4096 byte/deadline 5 detik, CSP origin sendiri, tanpa unsafe-inline/CDN, limiter SQLite, ownership cookie dan retensi tetap berlaku. POST /api/v8/download tetap 503; validasi hostname bukan bukti extractor. UI tidak menyimpan URL draft secara permanen atau menciptakan API audio/history.

Launcher selalu 127.0.0.1, tanpa trust forwarded headers dan tanpa access log request. --offline-workflow memberi akses Docker hanya untuk fixture lokal yang ditentukan kode. Bukan launcher deployment produksi.

## Docker dan verifikasi

Image web dibangun offline dari base lokal terverifikasi dan wheel dengan SHA-256 terpin, melalui build_image.py /absolute/wheelhouse. Daftar file eksplisit mengecualikan developer HTML/JS/CSS, arsip Tools, router legacy dan Docker client. staging.compose.yaml hanya network internal tanpa published port, runtime readonly/non-root/cap-drop ALL/NoNewPrivs dengan state tmpfs.

run_staging_test.py memeriksa entrypoint default; main(owned=True) memeriksa surface ownership. State tmpfs/limiter bukan kuota total host atau penyimpanan produksi. Dependensi/OS minimal, ingress TLS, filesystem quota, load/recovery dan sign-off masih diperlukan. Jangan menyimpulkan readiness publik dari tes fixture.

Kontrak ownership: [OWNERSHIP.md](OWNERSHIP.md). Backend gambar: [IMAGES.md](IMAGES.md). Roadmap: [MVP_READINESS.md](MVP_READINESS.md).
