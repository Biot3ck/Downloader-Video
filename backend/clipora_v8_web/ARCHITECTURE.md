# Arsitektur Clipora v8

Dokumen ini menjelaskan komponen, alur data, dan batas kepercayaan. Kondisi terkini dan blocker
ada di [STATUS.md](STATUS.md); rincian audit ada di [docs/](docs/).

## Prinsip

1. **Fail closed.** Route yang belum aman mengembalikan `503`, bukan perilaku parsial.
2. **Satu origin persis.** Host dan Origin setiap request dibandingkan dengan nilai konfigurasi,
   bukan pola atau wildcard.
3. **Boundary di luar aplikasi.** Header keamanan, batas body, dan penolakan scope non-HTTP
   dipasang sebagai pembungkus ASGI, sehingga route baru tidak bisa melewatinya.
4. **State privat.** Direktori state harus kanonis, milik UID proses, mode `0700`; database `0600`.
5. **Publikasi atomik.** Artifact hanya terlihat setelah transaksi database menandainya selesai.

## Komponen

| Modul | Tanggung jawab |
| --- | --- |
| `main.py` | `Boundary` (ASGI), CSP/header, `validate_origin`, route produk, `/api/v8/validate`, gate `503`, `app_factory` |
| `owned_api.py` | Factory surface ownership: sesi, status, cancel, download ber-otorisasi |
| `owned_jobs.py` | `OwnedJobs(JobStore)` — sesi, identitas, idempotensi, retensi |
| `owned_runner.py` | Pengamat pembatalan dan fencing berhenti |
| `owned_publish.py` | Publikasi MP4 atomik dengan fence eksekusi |
| `owned_artifacts.py` | Sweep artifact idle dan retensi file |
| `rate_limit.py` | Limiter fixed-window SQLite, IP di-hash HMAC |
| `platforms.py` | Allowlist pengenalan URL platform |
| `clipora_v8_browser_real_mp4/job_store.py` | Queue durable: `_admit`, `connection`, `transaction`, `finish` |
| `clipora_v8_browser_real_mp4/artifact_delivery.py` | `PinnedVideoResponse` — pengiriman file yang dipin ke inode |

`OwnedJobs` memperluas `JobStore` lewat tiga titik: hook `_configure_connection` (pragma
`foreign_keys`, `max_page_count`), helper `_admit` (aturan kapasitas tunggal), dan override
`finish`/`delete_expired` yang menambahkan pemeriksaan ownership. Aturan kapasitas tidak
diduplikasi.

## Alur request

```
client
  │
  ▼
Boundary (ASGI)                      ← tolak scope websocket, Host/Origin persis,
  │                                    body >4096 byte, deadline, CSP + header
  ▼
FastAPI app
  ├── GET /, /app, /assets/*         → file statis produk
  ├── GET /healthz                   → ready_for_public_launch: false
  ├── POST /api/v8/validate          → recognize_media(), tanpa egress
  └── POST /api/v8/download          → 503 selalu
```

Surface ownership (`create_owned_app`) menambahkan route job di atas boundary yang sama. Route
`/dev` hanya didaftarkan bila `offline_sample_enabled` aktif, dan mode itu hanya bisa dicapai
lewat launcher loopback.

## Alur job offline

```
POST /api/v8/owned/session   → cookie identitas (HMAC)
POST /api/v8/owned/jobs      → OwnedJobs.submit: cek ownership + kapasitas, catat idempotensi
                             → runner menjalankan worker terisolasi
owned_runner.observe         → polling status, batas waktu, stop ter-fence
owned_publish.publish        → validasi file, rename atomik, tandai selesai dalam transaksi
GET  .../download            → PinnedVideoResponse (inode dipin, Range/HEAD)
```

Worker tidak pernah menerima URL dari HTTP publik. Pada paket ini job hanya diisi oleh kode
trusted dalam tes atau fixture container.

## Batas kepercayaan

| Batas | Kontrol |
| --- | --- |
| Client → web | Host/Origin persis, body 4096 byte, deadline 5 detik, limiter per-IP (HMAC) |
| Web → worker | Worker terisolasi; tidak ada Docker socket di web tier; tidak ada egress dari web |
| Web → filesystem | State kanonis tanpa symlink, `0700`/`0600`, `O_NOFOLLOW`, pemeriksaan tipe file |
| Worker → artifact | Publikasi ter-fence oleh `execution_owner`; file parsial tidak pernah disajikan |
| Operator → host | **Tidak dimodelkan.** Root/operator Docker berada di luar batas ini |

## Build dan image

- `base_image.lock` adalah satu-satunya sumber digest base image.
- `build_image.py` memverifikasi digest base, memastikan `FROM` di `Dockerfile` cocok, lalu
  membangun image dari wheel yang hash-nya terpin di `requirements-web.lock`, tanpa network.
- Entrypoint default: `uvicorn clipora_v8_web.main:app_factory --factory`. Tidak ada aplikasi
  yang dibangun saat modul diimpor.
- `owned_entry.py` adalah entrypoint eksplisit untuk surface ownership.

Deviasi yang diketahui: image web masih mewarisi image worker, sehingga FFmpeg dan library codec
ikut terbawa. Lihat [STATUS.md](STATUS.md).

## Yang sengaja tidak ada

Tidak ada router legacy, akses Docker, scheduler, atau dependensi jaringan keluar di surface
produk. Tidak ada API audio/history. Tidak ada unggahan file dari browser. `clipora_v8_formats_lab`
adalah kandidat terpisah dan tidak diimpor aplikasi.
