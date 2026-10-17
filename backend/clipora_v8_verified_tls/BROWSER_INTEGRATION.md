# Clipora — integrasi TLS terverifikasi ke browser offline

## Hasil

Endpoint `/api/v8/real-offline/jobs` kini memakai runner `clipora_v8_verified_tls/run_browser_verified.py`. Kontrak endpoint, job ID, status URL, download URL, marker artifact, dan TTL 15 menit dipertahankan. Runner baru mendukung Docker langsung serta Compose sesuai flag CLIPORA_V8_USE_COMPOSE. Keduanya diuji dengan worker v8 dan Docker sebenarnya.

API memerlukan marker `CLIPORA_BROWSER_TLS_VERIFIED=1` pada baris utuh selain marker lama. Tidak ada fallback otomatis ke runner lama jika tes TLS atau runner gagal. Keberadaan marker adalah kontrak runner lokal yang dikendalikan aplikasi, bukan attestation kriptografis.

CA dan sertifikat server sementara dibuat per job. Verifikasi hostname dan sertifikat tetap aktif; CA tidak diinstal ke host atau image. Worker hanya menerima sertifikat CA publik. Tidak ada akses internet atau unduhan image; container memakai image lokal dengan pull never.

## Pengujian

- Runner browser mode Compose berhasil menghasilkan MP4.
- Runner browser mode Docker langsung berhasil menghasilkan MP4.
- Melalui UI asli `/app`, tombol Generate sample MP4 membuat job Compose yang selesai. Preview menampilkan video fixture biru dan kontrol pemutar aktif. Tombol Save MP4 ditekan.
- Respons file dari job UI diunduh melalui pemeriksaan HTTP API terpisah: 200, video/mp4, Content-Disposition attachment. Isi 11.528 byte identik dengan fixture. Range bytes=0-15 menghasilkan 206 dan byte yang benar.
- Lima tes kontrak baru lulus: delivery/range, penolakan marker lama, kegagalan runner tanpa retry tidak aman, expiry/symlink, gate offline nonaktif.
- Tiga kasus Docker TLS diulang: valid menghasilkan MP4; hostname salah dan CA tidak dipercaya ditolak tanpa MP4.
- Delapan tes API lama dan empat belas tes relay lulus. Total 27 tes otomatis, tiga kasus TLS Docker, dua uji runner browser, dan satu job UI nyata.
- Endpoint public download tetap mengembalikan 503. Audit readiness tetap 26/32, NOT READY.

QA browser memakai aplikasi FastAPI asli pada 127.0.0.1:8047. Thread sweeper router lama dan cleanup staging real-offline dinonaktifkan hanya dalam proses QA sementara agar artefak lama tidak terhapus saat pemeriksaan. Kontrak cleanup sebenarnya diuji dengan direktori temporary terpisah. Ini berarti tes browser tidak membuktikan expiry saat streaming serentak; race cleanup/FileResponse tetap pekerjaan lanjutan.

Server QA sudah dihentikan. Container/network uji tidak tersisa; lima container lama tetap berjalan. Artefak dari dua uji runner langsung dihapus berdasarkan tag milik tes ini. Artifact job browser masih mengikuti TTL staging yang sudah ada; salinan sample deliverable disimpan di outputs. Tidak ada berkas lama yang dihapus.

## Perubahan sumber

Diubah: `clipora_v8_browser_real_mp4/routes.py`, `clipora_v8_verified_tls/run_verified_tls.py` (opsi export artifact), dan README paket TLS.

Ditambah: `clipora_v8_verified_tls/run_browser_verified.py`, `test_browser_contract.py`, serta catatan integrasi ini.

Runner lama, Compose lama, worker, gateway, egress staging, frontend dan v7 tidak diubah pada tahap ini. Dibanding baseline audit pertama, perubahan sumber lama hanya main_v8.py (UI), server_stage.py (relay), dan routes.py (integrasi ini). Sumber baru yang ditambahkan setelah snapshot tidak tercakup baseline awal; manifest tahap ini mencatat file relevan.

## Menjalankan

Dari backend, pastikan tidak ada job aktif sebelum merestart server v8 milik Anda:

```sh
CLIPORA_V8_OFFLINE_BROWSER_TEST=1 CLIPORA_V8_USE_COMPOSE=1 .venv/bin/python -B -m uvicorn clipora_v8_fastapi_mvp.main_v8:app --host 127.0.0.1 --port 8088
```

Buka `/app` pada localhost:8088. Gunakan flag CLIPORA_V8_USE_COMPOSE=0 untuk mode Docker langsung. Memerlukan openssl dan ffprobe di host selain Docker serta tiga image fixture yang sudah ada. Tidak ada pemasangan paket baru pada tahap ini.

Tes kontrak tanpa Docker:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_verified_tls -p test_browser_contract.py -v
```

## Batas dan langkah berikutnya

Perubahan berlaku untuk endpoint **real-offline**, bukan semua tombol eksperimen di `/dev`. Endpoint local-mp4 dan offline-e2e lama tetap tidak diubah; fixture lama yang memiliki pengecualian TLS masih tersimpan sebagai referensi, tetapi tidak dipakai runner real-offline baru.

Unduhan publik hybrid belum diaktifkan. DNS/redirect, firewall independen Linux, kuota disk keras, job persisten, dan cleanup saat streaming masih memerlukan pekerjaan serta pengujian. Tidak ada perubahan VPS atau deployment.

## Rollback

Pulihkan routes.py dan run_verified_tls.py dari dua salinan sebelum integrasi di outputs. Jangan memulihkan v7, frontend, atau perbaikan relay. Runner lama tetap tersedia; rollback tersebut akan mengembalikan pemilihan runner lama beserta keterbatasan TLS fixture sebelumnya. Hentikan job yang aktif terlebih dahulu dan jangan menjalankan rollback otomatis ke jalur lama saat TLS gagal.
