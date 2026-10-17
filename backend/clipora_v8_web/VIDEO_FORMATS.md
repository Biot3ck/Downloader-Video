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
