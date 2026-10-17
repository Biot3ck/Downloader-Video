# Clipora v8 — surface produk web

Clipora adalah antarmuka downloader untuk video dan foto dari YouTube, TikTok, Instagram dan
Pinterest. **Unduhan publik sengaja dinonaktifkan pada paket ini.** Yang aktif hanya pengenalan
link dan pemeriksaan platform; tidak ada ekstraksi, konversi, iklan, atau penulisan file media.

| Surface | Status |
| --- | --- |
| `POST /api/v8/download` | Selalu `503` (gate publik tertutup) |
| `/api/v8/validate` | Aktif — hanya mengenali platform |
| Video & Photo Downloader | Aktif sampai tahap pemeriksaan link |
| Mode demo (`--demo-downloads`) | Opsional — preview dan file contoh lokal, bukan isi post |
| Audio Downloader & History | Belum tersedia, ditandai `Soon` di navigasi |
| `/healthz` | `ready_for_public_launch: false` |

Status lengkap, angka tes, dan blocker ada di [STATUS.md](STATUS.md). Keputusan desain dan batas
kepercayaan ada di [ARCHITECTURE.md](ARCHITECTURE.md).

## Menjalankan lokal

Dari direktori `backend`:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090
```

Buka <http://127.0.0.1:8090>. Launcher selalu mengikat `127.0.0.1`, tidak mempercayai forwarded
header, dan tidak menulis access log request.

Untuk utilitas developer (job queue, ownership, worker sampel lokal):

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090 \
  --offline-workflow --state /absolute/private/state
```

`/dev` hanya tersedia pada mode itu dan hanya lewat HTTP loopback. Halaman produk tidak pernah
memuat fixture, dan `--offline-workflow` tidak mengaktifkan internet.

### Mode demo unduhan

Untuk mencoba alur lengkap (tempel link → preview + caption → pilih Video/Video HD/MP3 → file
terunduh) tanpa menyentuh internet, jalankan dengan flag demo:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090 --demo-downloads
```

Mode ini menambahkan empat route loopback-only:

| Route | Perilaku |
| --- | --- |
| `POST /api/v8/demo/preview` | Memvalidasi link, mengembalikan caption contoh dan URL preview bertanda tangan HMAC |
| `GET /api/v8/demo/preview/<token>` | Mengirim sampel secara inline untuk elemen `<video>`/`<img>` |
| `POST /api/v8/demo/download` | Memvalidasi link, mengembalikan URL unduhan bertanda tangan HMAC (berlaku 5 menit) |
| `GET /api/v8/demo/file/<token>` | Mengirim salah satu dari empat file contoh di `assets/demo/` sebagai lampiran |

File dan caption yang ditampilkan adalah **sampel yang dibundel di repo**, bukan isi post yang
ditempel. UI menyebutkan hal ini secara eksplisit, dan `POST /api/v8/download` tetap `503`. Route
demo tidak pernah didaftarkan pada origin HTTPS, container, atau tanpa flag. Flag ini juga tidak
bisa digabung dengan `--offline-workflow`.

Tombol **Paste** membaca clipboard lewat `navigator.clipboard.readText()` lalu langsung memeriksa
link. Browser bisa menolak akses clipboard; dalam hal itu UI meminta pengguna menempel manual
dengan Cmd+V. Clipboard hanya dibaca setelah tombol ditekan, tidak ada pembacaan otomatis.

## Menjalankan tes

Dari direktori `backend`:

```sh
.venv/bin/python -B -m unittest discover -s clipora_v8_web -p 'test*.py' -q
node clipora_v8_web/test_frontend_async.cjs
```

Paket lain diuji dengan pola yang sama (`clipora_v8_firewall_candidate`,
`clipora_v8_verified_tls`, `clipora_v8_secure_egress_stage`, `clipora_v8_image_backend`,
`clipora_v8_local_workflow`, `clipora_v8_staging_linux`, `clipora_v8_formats_lab`).

## Struktur

```
backend/
  clipora_v8_web/              surface produk: ASGI boundary, API, UI, limiter
  clipora_v8_browser_real_mp4/ queue durable dan pengiriman artifact
  clipora_v8_local_workflow/   launcher alur offline (sampel lokal)
  clipora_v8_image_backend/    pipeline gambar offline
  clipora_v8_verified_tls/     fixture TLS/worker terverifikasi
  clipora_v8_secure_egress_stage/ stage egress dan parser HTTP
  clipora_v8_firewall_candidate/ kandidat three-tier kernel/mTLS
  clipora_v8_staging_linux/    preflight host Linux
  clipora_v8_formats_lab/      kandidat kebijakan format (tidak diimpor produk)
```

## Dokumentasi

- [STATUS.md](STATUS.md) — kondisi terkini, tes, blocker, deviasi yang diketahui
- [ARCHITECTURE.md](ARCHITECTURE.md) — komponen, alur data, batas kepercayaan
- [docs/RELEASE_SECURITY.md](docs/RELEASE_SECURITY.md) — review keamanan dan blocker publik
- [docs/OWNERSHIP.md](docs/OWNERSHIP.md) — kontrak ownership, sesi, idempotensi
- [docs/CANCELLATION.md](docs/CANCELLATION.md) — pembatalan dan fencing worker
- [docs/IMAGES.md](docs/IMAGES.md) — pipeline gambar offline
- [docs/OS_PACKAGE_REVIEW.md](docs/OS_PACKAGE_REVIEW.md) — review paket OS dan patch tertunda
- [docs/UI_RESTRUCTURE.md](docs/UI_RESTRUCTURE.md) — catatan restrukturisasi UI
- [docs/VIDEO_FORMATS.md](docs/VIDEO_FORMATS.md) — kandidat kualitas video/MP3
- [docs/MVP_READINESS.md](docs/MVP_READINESS.md) — riwayat milestone dan rencana

## Batas keamanan

Origin dikonfigurasi sebagai satu nilai persis; Host dan Origin setiap request harus cocok
dengannya. Body POST dibatasi 4096 byte dengan deadline, CSP tanpa `unsafe-inline`/CDN dipasang
di lapisan ASGI, dan limiter memakai hash HMAC atas IP klien. State harus berupa path kanonis
tanpa symlink, direktori milik UID proses dengan mode `0700`, dan database `0600`.

Ini bukan klaim siap produksi. Enam blocker pada [STATUS.md](STATUS.md) belum dapat ditutup tanpa
host staging Linux terpisah.
