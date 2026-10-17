# Clipora — penguatan DNS, redirect, dan penyimpanan offline

## Yang selesai

1. **DNS staging:** hostname ambigu (bentuk numerik alternatif, trailing dot, label kosong/terlalu panjang, tanda hubung tidak valid) ditolak sebelum resolusi. NXDOMAIN atau timeout pada salah satu keluarga A/AAAA menggagalkan seluruh hasil, termasuk jawaban parsial. NoAnswer tetap boleh memakai jawaban aman dari keluarga lain.
2. **Deny sebelum DNS:** transport default staging langsung mengembalikan 403 sebelum query DNS. Jalur tes yang menyuntikkan resolver/dial tetap memvalidasi semua alamat sebelum menghubungkan satu IP numerik dari snapshot; tes memastikan tidak ada lookup kedua atau fallback IP setelah dial gagal.
3. **Redirect:** fixture Docker baru mencakup redirect aman satu host, alamat metadata privat, host lain, HTTP downgrade, dan loop. Dua hasil aman menghasilkan MP4; enam kasus negatif (termasuk hostname/CA salah) ditolak. Target berbahaya hanya nilai Location sintetik; gateway fixture menolak request sebelum egress menuju target itu.
4. **Workspace worker:** runner terverifikasi Docker langsung dan Compose memakai /output tmpfs 64 MiB dengan nosuid,nodev,noexec, user non-root, root filesystem read-only, cap-drop ALL, no-new-privileges, dan jaringan internal. Worker tidak lagi memiliki bind mount output yang dapat ditulis di host. Kernel memberi batas nyata pada workspace, yang juga dihitung ke penggunaan memori container.
5. **Ekspor hasil:** worker tetap hidup sebentar setelah sukses agar file tmpfs dapat diekspor, lalu runner menghapus container. Deadline collector 60 detik dan hold worker 90 detik. Ekspor membaca satu path job terverifikasi dengan O_NOFOLLOW, validasi tipe/ukuran, dan batas 64 MiB. Docker Desktop tidak dapat mengarsipkan tmpfs melalui docker cp pada percobaan ini; docker exec dipakai untuk reader tetap yang terbatas. Tidak ada fallback ke bind mount writable atau penonaktifan TLS.
6. **Staging browser:** batas aplikasi 64 MiB dan 32 file. Publikasi memakai flock lintas proses, file sementara, dan hard link atomik tanpa overwrite. Ukuran diperiksa di bawah lock; sumber/staging symlink dan entry non-regular ditolak. Kegagalan publikasi membersihkan file sementara milik operasi itu. File parsial dari proses yang dibunuh mendadak tetap dihitung dalam anggaran berikutnya, sehingga gagal tertutup; belum ada pembersihan orphan parsial otomatis.
7. **API:** staging penuh atau mencapai batas file menghasilkan 507 sebelum worker dijadwalkan. Gate publik tetap 503. Endpoint dan kontrak UI tidak berubah.

## Hasil tes

- 25 tes staging (DNS + relay) lulus.
- 15 tes kontrak browser dan staging budget lulus, termasuk dua proses nyata yang bersaing pada anggaran sama: hanya satu publikasi boleh berhasil.
- 8 tes API v8 lulus. Total **48 tes unit/API**.
- **8 kasus Docker TLS/redirect** lulus sesudah migrasi workspace tmpfs: valid, wrong-host, untrusted-ca, redirect-safe, redirect-private, redirect-other-host, redirect-http, redirect-loop.
- Uji kernel dengan tmpfs 1 MiB berhasil memicu ENOSPC dan memverifikasi root filesystem menolak tulis dengan EROFS. Uji ini memakai network none dan tidak memasang filesystem host.
- Runner Compose browser dengan workspace 64 MiB berhasil membuat MP4.
- Job API nyata (TestClient → Compose → worker → staging) selesai. Download 11.528 byte identik dengan fixture; Range menghasilkan 206; public download tetap 503.
- QA API nyata menonaktifkan cleanup staging dan sweeper router lama hanya di proses QA agar artefak lama tidak terhapus. Tes expiry/cleanup sendiri memakai direktori temporary terpisah. Tidak ada tes browser visual baru karena frontend tidak berubah; playback browser telah diverifikasi pada tahap integrasi sebelumnya.

Semua container/network tes dibersihkan. Lima container lama tetap berjalan. Artefak dari tes ini dibersihkan berdasarkan tag milik tes; file lama tidak dihapus.

## Batas bukti

DNS memakai jawaban sintetik yang disuntikkan; tidak ada query ke DNS publik. Redirect berbahaya ditolak oleh gateway fixture yang hanya mengizinkan example.com. Ini membuktikan batas jalur fixture, bukan kebijakan domain/CDN produksi untuk TikTok/Instagram/Pinterest.

Tmpfs membatasi workspace **per worker fixture**, bukan seluruh disk host atau semua worker lama. /tmp memiliki batas tmpfs tersendiri; aplikasi masih perlu batas concurrency global dan ukuran memori/transfer yang konsisten untuk penggunaan publik. Hasil ekspor maksimal 64 MiB sementara dapat berada dalam memori proses collector.

Batas staging adalah aturan aplikasi untuk runner yang memakai staging_store.py. Itu bukan kuota filesystem terhadap proses lain yang menulis ke folder yang sama. Kebijakan hard quota produksi dan sustained-load testing masih diperlukan.

Audit publik tetap **26/32, NOT READY**. Gate audit produksi sengaja tidak diubah hanya karena tes offline lulus. Firewall Linux independen, bypass routing, kebijakan allowlist domain/CDN, job persisten/global, dan cleanup aman saat streaming masih terbuka. VPS, deployment, dan unduhan publik tidak disentuh.

## Berkas relevan

Diperbarui: clipora_v8_secure_egress_stage/connect_policy.py, dns_policy_v2.py, server_stage.py; clipora_v8_browser_real_mp4/routes.py; clipora_v8_verified_tls/egress_fixture.py, worker_verified.py, run_verified_tls.py, run_browser_verified.py, test_browser_contract.py.

Ditambahkan: test_dns_boundary.py pada staging; bounded_worker.py, staging_store.py, test_staging_store.py, run_workspace_quota.py pada paket TLS.

v7, worker produksi/root, gateway/egress live deny-all, Compose lama, runner lama dan frontend tidak diubah. Snapshot audit awal tetap tidak dimodifikasi: perbedaan sumber lama hanya main_v8.py, routes.py, dan tiga modul staging yang disebutkan. Sumber baru tercatat pada manifest tahap ini.

## Menjalankan ulang

Dari backend:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_secure_egress_stage -p 'test*.py' -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_verified_tls -p 'test*.py' -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_ui_baseline/test_ui_api.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_verified_tls/run_verified_tls.py --redirects
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_verified_tls/run_workspace_quota.py
```

Server v8 tetap dijalankan hanya di localhost dengan flag offline yang sudah didokumentasikan. Tidak ada server QA yang dibiarkan berjalan oleh tahap ini.

## Rollback

Arsip clipora-dns-quota-before.zip menyimpan delapan sumber runtime yang diubah sebelum tahap ini dengan path relatif backend. Pulihkan hanya setelah job v8 selesai, lalu restart server v8 bila diperlukan. File tambahan boleh dibiarkan karena sumber lama tidak mereferensikannya. Test baru/test tambahan mengharapkan hardening ini dan dapat gagal setelah rollback; arsip bukan snapshot seluruh proyek. Jangan rollback v7 atau mengaktifkan fallback tidak aman saat TLS gagal.
