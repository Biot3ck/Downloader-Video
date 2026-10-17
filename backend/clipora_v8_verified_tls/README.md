> Pembaruan: lihat [FAULTS_AND_BUNDLES.md](FAULTS_AND_BUNDLES.md) untuk bundle runtime minimal, uji SIGKILL proses nyata, dan uji admission multiproses.

> Pembaruan durable job: lihat DURABLE_JOBS.md. Endpoint real-offline kini memakai SQLite, satu runner lintas proses, dan file delivery ber-lock; job in-flight yang terputus gagal dengan aman setelah cleanup, tanpa retry otomatis.

> Pembaruan: lihat DNS_QUOTA_HARDENING.md untuk kondisi terbaru. Workspace runner kini tmpfs 64 MiB, bukan bind mount dengan monitor berkala; staging memakai batas aplikasi 64 MiB/32 file dan publikasi atomik. Bagian di bawah merekam milestone TLS awal.

# Clipora v8 — TLS terverifikasi melalui Docker offline

## Hasil

Tiga kasus dijalankan melalui worker v8 asli → gateway fixture → Secure Egress staging → HTTPS fixture, dalam container Docker lokal. Semua lulus:

| Kasus | Hasil |
| --- | --- |
| CA dipercaya, SAN example.com sesuai | Worker process_video menghasilkan MP4 11.528 byte; ffprobe mengonfirmasi H.264/yuv420p |
| CA dipercaya, SAN wrong.example.com | yt-dlp menolak hostname; tidak ada MP4 yang dibuat |
| CA tidak dipercaya | yt-dlp menolak sertifikat; tidak ada MP4 yang dibuat |

Tes negatif memeriksa pesan certificate verification failure secara eksplisit. Gagal karena koneksi terputus saja tidak dihitung sebagai tes lulus.

Tambahan 14 tes relay/staging dan 8 tes API lulus. Total: 3 kasus Docker + 22 tes regresi.

## Implementasi

Paket baru: backend/clipora_v8_verified_tls/

- run_verified_tls.py: membuat CA dan sertifikat server sementara, menjalankan tiga kasus Docker, memeriksa MP4 dan cleanup.
- worker_verified.py: adaptor khusus tes untuk worker asli. URL hanya example.com/video.mp4; validasi URL produksi diganti hanya di proses fixture agar URL sintetik ini boleh dipakai. nocheckcertificate tetap False.
- egress_fixture.py: adaptor baru yang memakai handle() staging dan sertifikat sementara. Resolver/dial tes hanya memetakan target example.com:443 dan IP sintetik 8.8.8.8 ke HTTPS fixture di localhost. Ini tidak menguji DNS publik.

Konfigurasi yt-dlp no-certifi memilih mekanisme trust sistem dalam proses tes; SSL_CERT_FILE menunjuk CA fixture yang eksplisit dan SSL_CERT_DIR menunjuk direktori kosong. Konfigurasi ini tidak mematikan validasi sertifikat atau hostname, tidak menginstal CA, dan tidak mengubah trust store host/image.

CA/private key dibuat ulang setiap run dan dihapus bersama direktori sementara setelah pengujian. Private key CA tidak dipasang ke container. Server hanya menerima key/cert server; worker hanya menerima sertifikat CA publik.

Dua jaringan Docker dibuat dengan internal=true. Worker hanya berada di jaringan worker–gateway, egress hanya di jaringan gateway–egress. Tidak ada port yang dipublikasikan. Container memakai user non-root host, filesystem read-only, cap-drop ALL, no-new-privileges, batas CPU, memori dan PID; output fixture dibatasi monitor 64 MiB. Monitor tersebut bukan kuota disk keras.

Image harus sudah tersedia; --pull never mencegah pengunduhan image otomatis. Tidak ada image yang dibangun, paket yang diinstal, atau koneksi ke platform publik.

## Menjalankan ulang

Dari backend:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_verified_tls/run_verified_tls.py
```

Opsional tambahkan --report /path/absolut/hasil.json. Gunakan lokasi baru atau hasil tes yang memang boleh ditimpa.

Memerlukan Docker yang berjalan, openssl, ffprobe, serta image lokal clipora-worker:v8-dns, clipora-gateway:v8-test, clipora-dns-wire:v8-test. Tidak perlu memasang dependensi baru.

## Perlindungan baseline dan cleanup

Tidak ada sumber lama yang diubah pada tahap ini. Dibanding snapshot awal, perbedaan tetap hanya main_v8.py dari tahap UI dan server_stage.py dari perbaikan relay sebelumnya. Checksum relay masih cocok dengan manifest perbaikan terakhir. v7, runner browser, worker, Compose, firewall dan fixture lama tetap utuh.

Sesudah suite selesai, tidak ada container/network dengan prefix clipora-vtls- yang tersisa. Lima container proyek yang sudah berjalan sebelumnya tetap berjalan. Semua output MP4 tes dihapus setelah pemeriksaan.

## Batas hasil

Ini memvalidasi TLS client yt-dlp dan worker aktual pada alur Docker offline, bukan kesiapan produksi atau download dari platform sebenarnya. Gateway masih fixture dengan target tunggal; resolver/dial disuntikkan untuk memetakan target ke fixture. Tidak membuktikan DNS publik, rebinding, redirect lintas domain, firewall publik, maupun hard quota.

Pembaruan integrasi: endpoint real-offline browser kini memakai run_browser_verified.py (lihat BROWSER_INTEGRATION.md). Runner lama dengan pengecualian sertifikat tetap disimpan sebagai referensi dan tidak dipakai jalur real-offline baru. Sertifikat statis fixture lama tidak dipakai oleh paket baru, sehingga kedaluwarsanya tidak merusak suite baru.

Audit kesiapan publik tetap 26/32, NOT READY. Gate TLS produksi pada audit tetap gagal karena bukti offline tidak sama dengan bukti runtime produksi. Public egress tetap tertutup. Tidak ada perubahan VPS/deployment.

## Langkah berikutnya

Integrasi real-offline browser telah selesai dan diuji (lihat BROWSER_INTEGRATION.md). Lanjutkan DNS/redirect dan kuota keras sebelum mempertimbangkan aktivasi unduhan publik.

## Rollback

Tidak perlu memulihkan sumber lama: paket baru belum direferensikan aplikasi atau runner lama. Hentikan pemakaian paket baru bila perlu. Jangan menghapus atau mengubah runner offline lama.
