> Catatan: dokumen ini menyimpan rincian audit pada saat penulisannya. Status, angka tes, dan blocker terkini ada di [STATUS.md](../STATUS.md).

# Video, Video HD, dan MP3

## Status sekarang

Halaman Video menyediakan tiga radio pilihan: Video, Video HD, MP3. Pilihan adalah preferensi tampilan, bukan klaim format tersedia. Penjelasan unavailable berubah sesuai pilihan. Pada Photo kontrol disembunyikan; halaman Audio tetap disabled. Tidak ada iklan, konversi, submit download, izin HD, API baru, atau penyimpanan pilihan permanen.

Check link tetap hanya POST /api/v8/validate dengan url dan media_kind=video, termasuk ketika MP3 dipilih: yang diperiksa adalah platform sumber video, bukan kemampuan ekstraksi audio. Mengubah pilihan membatalkan pemeriksaan berjalan dan membersihkan hasil lama. Tidak mengubah backend atau gate 503.

## Rancangan integrasi setelah keamanan publik diterima

1. Ambil metadata/format melalui worker dan jalur Gateway/Secure Egress yang sudah diterima audit. Metadata tidak memberi izin melewati validasi DNS/redirect/TLS, batas sumber daya, atau kepemilikan job.
2. Tawarkan Video standar sampai 480p hanya bila format sumber tersedia. Hindari encoding ulang untuk MVP. Jangan menjanjikan 480p ketika sumber hanya menyediakan 1080p; tampilkan pilihan yang benar-benar tersedia.
3. Tawarkan HD 720p/Full HD 1080p hanya bila format sumber lebih tinggi daripada pilihan standar. Gunakan dimensi sisi pendek agar portrait dan landscape konsisten. Resolusi, codec, bitrate dan estimasi ukuran berasal dari metadata; hasil akhir diperiksa dengan ffprobe dalam isolasi. Jangan upscale atau fallback diam-diam ke resolusi rendah lalu melabelinya HD. Resolusi sumber tidak membuktikan bahwa pemilik sumber tidak pernah melakukan upscale sebelumnya.
4. Periksa ketersediaan dan kapasitas sebelum menawarkan rewarded ad. Mulai dengan satu iklan opsional untuk satu unduhan HD. Jika provider tidak menyediakan iklan, pilihan standar tetap tersedia. Gagal menghasilkan HD harus ditangani tanpa meminta iklan ulang otomatis.
5. Pilih provider yang menerima model bisnis/reward ini. Verifikasi reward sesuai mekanisme resmi provider; timer, event frontend atau boolean dari browser tidak cukup. Jika provider tidak mendukung verifikasi yang dapat dipercaya, jangan aktifkan unlock produksi. Izin server terikat sesi, job dan format, berumur pendek, sekali pakai dan tahan replay. URL/file akhir tetap memerlukan ownership; jangan mengirim cookie, URL video, atau data pribadi ke provider.
6. MP3 memerlukan jalur FFmpeg audio terbatas CPU/waktu/ukuran, tanpa jaringan langsung. Tampilkan bitrate hanya setelah tersedia dan tervalidasi; konversi tidak meningkatkan kualitas audio sumber. Untuk video+audio HD prioritaskan merge tanpa encoding ulang jika codec/container kompatibel.

Rewarded ad dan pilihan format tidak menjadi pengganti gate keamanan. Integrasi provider/CSP dan pemrosesan format belum diaktifkan. V7 dan workflow sampel offline tetap dipertahankan.

## Verifikasi perubahan UI

63 tes Python web dan 7 unit test JavaScript lulus. Tes JavaScript memastikan pilihan HD/MP3 hanya memakai kontrak pengenalan URL yang sudah ada dan tidak membuat request download/iklan. Image web dibangun offline dan kedua entrypoint Docker diuji ulang. Browser aktual memeriksa pilihan HD/MP3, tombol panah keyboard, pilihan tersembunyi di Photo, serta lebar 1280/768/390/320 tanpa overflow horizontal. Viewport pengujian di-reset; tab pengguna tidak diubah.

## Kandidat backend offline

Perencana kandidat kini berada di paket terpisah `../clipora_v8_formats_lab/` (tidak diimpor aplikasi, tidak disajikan HTTP, tidak masuk image). `video_formats.py` menambahkan perencana murni tanpa I/O: maksimal 256 format, durasi 30 menit, estimasi/file akhir maksimal 64 MiB. MVP kandidat hanya menerima H264/AAC MP4 dengan status non-DRM eksplisit; codec lain belum didukung. Video standar memilih format asli sampai sisi pendek 480 px, HD 720–1080 px dengan sisi panjang maksimal 1920 px. Video-only memerlukan audio AAC kompatibel; format progressive yang mempunyai audio dapat langsung dipilih. Jika tidak tersedia tidak membuat fallback/upscale. Estimasi ukuran yang tidak diketahui tetap None, bukan angka palsu, dan belum menggantikan batas byte saat download.

verify_output memeriksa JSON ffprobe dari runner tepercaya: codec/container, audio/video stream, dimensi sesuai pilihan, durasi dan ukuran. MP3 harus benar-benar berisi satu stream MP3, bukan MP4 yang diganti nama. Pemeriksaan metadata ini tidak menggantikan decode penuh, pemeriksaan inode/path, fencing/ownership atau hard limit worker. Plan tidak berisi URL, header, cookie atau secret dan tidak memberikan hak HD/iklan.

Modul kandidat (`clipora_v8_formats_lab`) tidak diimpor aplikasi/worker aktif, tidak disajikan HTTP dan tidak dimasukkan build_image.py. Belum ada submit, publication/delivery/cleanup MP3 atau integrasi metadata publik, merge stream terpisah, rewarded ad dan quota produksi. Batas encoding/format ini perlu diuji dengan extractor sesungguhnya di staging sebelum dihubungkan ke job. Jangan menyimpulkan readiness publik dari fixture.

Pengujian aktual menggunakan FFmpeg/ffprobe di worker lokal terpin, network=none, readonly, non-root, cap-drop ALL, no-new-privileges, 1 CPU, 384 MiB, 64 PID dan tmpfs 64 MiB. Tiga sumber sintetis dibuat langsung pada 854×480, 1280×720, 1080×1920. Output video memakai stream copy, MP3 memakai konversi audio, semua hasil didecode penuh. Verifikasi menolak file 480p untuk plan HD dan MP4 untuk plan MP3. Tidak mengekspor fixture ke UI/download pengguna; worker sementara dibuang setelah pengujian.

Jalankan dari backend:

```sh
.venv/bin/python -B clipora_v8_formats_lab/run_formats_offline.py --report /absolute/path/report.json
```

Setelah penambahan kandidat: 71 tes Python web, 17 backend gambar, 6 workflow lokal dan 7 JavaScript lulus (101 total), ditambah pengujian FFmpeg offline aktual. Gate publik tetap 503, termasuk ketika klien mengirim reward_completed=true dan meminta hd/mp3.
