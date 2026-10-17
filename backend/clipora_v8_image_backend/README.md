# Backend album gambar — kandidat offline

Alur yang tersambung: UI Images / album → sesi browser → antrean durable yang sama dengan video → worker Docker tanpa jaringan → decode PNG/JPEG/WebP → ZIP/manifest → publikasi atomik → unduh gambar/ZIP milik sesi. Sampel berisi tiga gambar berwarna yang dibuat kode lokal, bukan konten TikTok/Instagram/Pinterest. Tidak ada extractor atau koneksi platform publik.

Preview loopback dengan `clipora_v8_web/run_local.py --offline-workflow` menyediakan tombol **Prepare sample album**. Launcher biasa/image web default tetap menyembunyikan sampel dan tidak memuat Docker launcher/paket backend gambar. Tidak ada dependency baru atau perubahan pada worker v7/v8 asli.

## Kontrak backend

- jobs.py memberi payload images terpisah dari video. Request gambar publik dapat disusun oleh kode trusted untuk persiapan, tetapi scheduler lokal menolaknya sebelum membuat resource. HTTP `/api/v8/samples/images` hanya menerima objek JSON kosong dan idempotency key; tidak menerima URL, path, manifest atau daftar CDN. Gate `/api/v8/download` tetap 503.
- Antrean, sesi, cancellation, idempotency, TTL, maksimum empat pending/satu per sesi dan satu processing global dipakai ulang. Sampel video dan gambar berbagi leader lock. Helper mewarisi fd lock agar recovery tidak berlomba dengan ekspor setelah web mati. Resource Docker terikat execution owner yang sama dan cleanup memeriksa ID/label.
- Worker non-root, readonly, cap-drop ALL, NoNewPrivs, network none, CPU 1, RAM 384 MiB, PID 64, output tmpfs 64 MiB. Hanya source Python eksplisit dan gambar fixture dibind readonly. FFmpeg memeriksa frame penuh dengan decoder dan protokol file/pipe eksplisit; stderr tidak diteruskan lewat API. PNG rusak dengan CRC container valid tetapi payload kompresi invalid ditolak decoder.
- Maksimum 20 gambar, 10 MiB/file, 50 MiB total, 16 MP/file, 32 MP total, sisi 16.384 piksel. PNG CRC/chunk/end, JPEG header/end, WebP RIFF/chunk diperiksa; APNG/WebP animasi, SVG/HTML, path traversal dan file/symlink nonregular ditolak. Decoder penuh dijalankan hanya di worker disposable, bukan handler HTTP.
- Satu ZIP stored memuat manifest version 1 dan item berurutan. Manifest hanya berisi posisi, nama hasil tetap, tipe, dimensi, ukuran dan SHA-256; tidak berisi URL, cookie, judul/nama asli atau path host. ZIP menolak kompresi, enkripsi, duplicate/extra entries dan file khusus. Gambar asli tidak dikonversi dalam produk. Generator fixture saja mengubah PNG buatan kode menjadi JPEG/WebP untuk tes. Metadata asli tetap dipertahankan.
- Publisher bersama video mendapat validator khusus ZIP; signature/limit MP4 tetap default. ZIP disalin ke inode sementara, hash/struktur diperiksa ulang, owner/status/cancel/expiry/payload diperiksa dalam transaksi yang sama, hardlink eksklusif+fsync lalu status completed. Tidak mengganti file yang sudah ada. Caller resource observer wajib mengonfirmasi worker/exporter berhenti sebelum publikasi.
- Read routes `/api/v8/jobs/{id}/images`, `/images/{position}`, `/album.zip` hanya dipasang pada launcher lokal eksplisit. Cookie pemilik diperiksa sebelum file dibuka. Gambar/ZIP memakai inode pin+shared flock, HEAD/Range dan nosniff/CSP boundary. Range gambar dibatasi satu rentang; range multi ditolak 416. Sweep kini mengenali ZIP dan MP4, menunda unlink saat reader memegang lock. Video tidak dapat diambil melalui route gambar dan sebaliknya.

## Reproduksi

Dari backend, tanpa mengaktifkan internet:

```sh
.venv/bin/python -B -m unittest discover -s clipora_v8_image_backend -p 'test*.py' -q
.venv/bin/python -B clipora_v8_image_backend/run_offline.py --report /absolute/new/decoder.json
.venv/bin/python -B -m clipora_v8_image_backend.run_workflow_test --report /absolute/new/cancel-video.json
```

17 tes backend gambar lulus. Decoder aktual menerima PNG/JPEG/WebP dan menolak PNG corrupt dalam Docker network none. Tes HTTP aktual memverifikasi manifest, byte gambar asli, ZIP, ownership, HEAD/Range. Pembatalan worker gambar aktual membersihkan resource sebelum failed dan tidak menyajikan file parsial; slot kemudian dipakai worker video aktual sampai MP4 selesai. 57 tes web dan enam local workflow tetap lulus. Image web default/owned diuji ulang. Browser aktual berhasil menyiapkan album dan menampilkan tiga gambar beserta link unduh.

## Belum siap publik

Pengambilan foto/carousel TikTok, Instagram dan Pinterest belum diimplementasikan atau diuji nyata. Jangan menyamakan validasi hostname/post URL dengan dukungan extractor. Langkah publik berikutnya memerlukan extractor yang seluruh request metadata/media/redirect melewati policy DNS/IP/TLS/CDN yang disetujui, staging Linux terpisah, kuota host total, beban/crash/controller/backup/ingress/dependency review dan persetujuan egress/deployment. Kuota worker bukan kuota DB/WAL/log/temp/artifact host. Preflight dan tes fixture ini tidak menutup enam blocker audit legacy. Fitur pemilih/preview file perangkat telah dihapus atas permintaan pemilik; galeri dan ZIP pada UI hanya menampilkan hasil backend.
