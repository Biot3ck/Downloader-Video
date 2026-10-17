# Clipora

Clipora adalah aplikasi web untuk mengunduh video dan foto dari YouTube, TikTok, Instagram dan
Pinterest. Repositori ini berisi surface produk web beserta paket pendukung untuk queue, ownership,
egress, TLS dan audit paket OS.

> **Status: demo internal.** Unduhan publik dinonaktifkan (`503`) dan `/healthz` melaporkan
> `ready_for_public_launch: false`. Enam bloker persetujuan publik belum dapat ditutup tanpa host
> staging Linux terpisah. Rincian ada di [STATUS.md](backend/clipora_v8_web/STATUS.md).
>
> Rencana menuju produk publik ada di [ROADMAP.md](ROADMAP.md). Analisis pasar dan strategi
> bersaing dengan snaptik.app ada di [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md).

## Isi repositori

```
backend/
  clipora_v8_web/                 surface produk: ASGI boundary, API, UI, limiter, docs
  clipora_v8_browser_real_mp4/    queue durable dan pengiriman artifact
  clipora_v8_local_workflow/      launcher alur offline
  clipora_v8_image_backend/       pipeline gambar offline
  clipora_v8_verified_tls/        fixture TLS dan worker terverifikasi
  clipora_v8_secure_egress_stage/ stage egress dan parser HTTP
  clipora_v8_firewall_candidate/  kandidat three-tier kernel/mTLS
  clipora_v8_staging_linux/       preflight host Linux
  clipora_v8_worker_integration/  integrasi worker
  clipora_v8_real_guarded_e2e/    harness e2e ter-guard
  clipora_v8_formats_lab/         kandidat kebijakan format (tidak diimpor produk)
```

Dokumentasi produk dimulai dari [backend/clipora_v8_web/README.md](backend/clipora_v8_web/README.md).

## Menjalankan lokal

```sh
cd backend
python3 -m venv .venv
.venv/bin/pip install -r ../requirements-dev.txt
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090
```

Buka <http://127.0.0.1:8090>. Launcher hanya mengikat loopback dan tidak mempercayai forwarded
header.

Untuk mencoba alur unduhan tanpa internet, tambahkan `--demo-downloads`:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090 --demo-downloads
```

Setelah link dikenali, opsi Video / Video HD / MP3 muncul dan tombol Download mengirim **file
contoh** yang dibundel di repo — bukan isi post asli. `POST /api/v8/download` tetap `503`.

## Menjalankan tes

```sh
cd backend
for pkg in clipora_v8_web clipora_v8_formats_lab clipora_v8_firewall_candidate \
           clipora_v8_verified_tls clipora_v8_secure_egress_stage \
           clipora_v8_staging_linux clipora_v8_image_backend \
           clipora_v8_local_workflow; do
  .venv/bin/python -B -m unittest discover -s "$pkg" -p 'test*.py' -q || exit 1
done
node clipora_v8_web/test_frontend_async.cjs
```

Angka tes terkini ada di [STATUS.md](backend/clipora_v8_web/STATUS.md).
