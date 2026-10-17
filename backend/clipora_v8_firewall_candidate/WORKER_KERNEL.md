# Worker v8 aktual melalui broker dan firewall kernel offline

17 Oktober 2026: run_worker_kernel.py menjalankan sumber real_download_worker_v8.py yang ada tanpa perubahan, melalui adapter worker_verified.py yang sudah dipakai suite offline. Bundel worker hanya berisi daftar runtime eksplisit; mount CA terpisah readonly; output berada di tmpfs 64 MiB dan /tmp 32 MiB. Root worker readonly, non-root, cap-drop ALL dan NoNewPrivs; memori/CPU/pids dibatasi. Pembaca output bounded yang ada digunakan untuk ekspor dan ffprobe memeriksa H.264/yuv420p.

Jalur yang diuji: worker yt-dlp -> gateway fixture -> CONNECT relay -> Broker -> DNS paket nyata -> grant melalui IPC privat -> filter table kernel -> socket numerik 8.8.8.8:443 -> HTTPS fixture. FFmpeg worker menghasilkan video.mp4 11528 byte pada kasus valid. Sertifikat/hostname tetap diverifikasi. Wrong-host dan untrusted-ca ditolak oleh yt-dlp, tanpa MP4 yang diekspor; pesan kesalahan sertifikat diperiksa. Kedua kasus negatif berhenti sebelum menghasilkan output FFmpeg.

Aturan tujuan port 443 harus sudah hilang sesudah worker selesai/gagal. Probe container tambahan berbagi namespace yang sama dan membuktikan koneksi TCP langsung diblokir setelah pencabutan. Seluruh container milik pengujian dihapus, container yang sudah ada dipertahankan. Sumber v7, worker, dan gateway fixture lama tidak diubah.

## Batas yang penting

Ini memakai network=none pada service container, kemudian worker berbagi namespace network container itu. Alias IP global terpasang pada loopback sehingga tidak ada akses ke pemilik IP internet. Gateway fixture masih proses dalam service child dan memakai loopback, bukan container jaringan tiga tier. Controller tetap root dengan capability firewall dalam namespace disposable; service child non-root/capability nol. Worker tidak mendapatkan mount socket IPC atau key CA, tetapi network sharing bukan isolasi worker/egress yang layak dipakai publik: izin aktif ke tujuan tidak terikat UID/proses worker. Jangan menganggap keberhasilan ini sebagai bukti anti-bypass selama lease aktif.

worker_verified.py membatasi input ke satu URL fixture dan memakai pengganti validator khusus tes yang sudah ada. Ini bukan uji extractor YouTube/TikTok/Instagram/Pinterest. Batas file 5 GiB pada worker lama belum mendapat kuota host sebesar itu; fixture memakai tmpfs 64 MiB. Public feature gate tidak berubah. Tidak ada deployment atau perubahan VPS.

## Reproduksi dari backend

```
.venv/bin/python -B clipora_v8_firewall_candidate/run_worker_kernel.py --case valid
.venv/bin/python -B clipora_v8_firewall_candidate/run_worker_kernel.py --case wrong-host
.venv/bin/python -B clipora_v8_firewall_candidate/run_worker_kernel.py --case untrusted-ca
```

Ketiga kasus lulus setelah perbaikan harness probe untuk worker yang memang sudah keluar pada kegagalan TLS. 43 tes unit kandidat juga lulus. Langkah integrasi berikutnya harus mengembalikan batas namespace tiga tier dan menguji bypass saat lease aktif sebelum mempertimbangkan aktivasi internet.
