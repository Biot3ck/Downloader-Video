# Clipora web staging

Target MVP yang dikonfirmasi: YouTube, TikTok, Instagram, Pinterest. Package ini menjadi kandidat permukaan web produk; `main_v8` lokal dan v7 tetap utuh. Tidak mengimpor router eksperimen, scheduler, Docker runner, atau yt-dlp. Public download selalu 503 dan health menyatakan belum siap launch.

Desain dan CSS berasal dari UI Clipora v8 yang sudah dipulihkan. Asset JS/CSS kini file terpisah agar CSP tidak membutuhkan unsafe-inline. UI menyediakan pengenalan link video/gambar pada empat platform. Fitur preview/save file perangkat dihapus sesuai permintaan pemilik. Pengenalan URL bukan pemeriksaan ketersediaan video atau bukti dukungan extractor; tidak ada DNS/HTTP ke platform. URL HTTPS dibatasi hostname input yang eksplisit; IP literal, userinfo, port eksplisit, host menyerupai domain resmi, backslash, dan karakter kontrol ditolak. Domain CDN/redirect belum diotorisasi oleh daftar ini.

## Menjalankan preview browser lokal

Dari backend:

```
.venv/bin/python -B clipora_v8_web/run_local.py --port 8090
```

Buka http://127.0.0.1:8090. Launcher selalu loopback, tanpa trust forwarded headers, access log request dinonaktifkan, concurrency 32 dan keepalive 5 detik. State limiter default berada di `clipora_v8_web_runtime`; gunakan `--state /absolute/path` untuk direktori lain. Launcher tidak memulai Docker atau worker video. Server ini untuk staging lokal, bukan perintah deployment publik.

## Batas HTTP

- Host harus sesuai origin tunggal yang dikonfigurasi. POST harus memiliki Origin yang persis sama; tidak ada CORS permisif.
- POST maksimum 4096 byte termasuk body streaming, deadline 5 detik, content encoding ditolak.
- CSP hanya script/style/connect origin sendiri, media dan gambar juga hanya origin sendiri. Tidak ada inline script/style, embed/frame, kamera, mikrofon, geolokasi, atau referrer keluar.
- GET `/dev`, `/docs`, `/openapi.json`, route demo/job offline tidak ada pada app ini.
- Admission POST: 20 per klien per 60 detik dan 120 global, fixed window. State SQLite dan transaksi BEGIN IMMEDIATE dipakai bersama antarproses pada host yang sama. Client berasal dari ASGI peer; forwarded headers diabaikan oleh launcher. IP di-HMAC dengan secret random per database, tidak disimpan plaintext. URL/nama file/isi media tidak disimpan dalam limiter. Baris window lama dibersihkan saat admission berikutnya. SQLite dibatasi 256 halaman x 4096 byte; batas ini bukan kuota host untuk seluruh produk. Busy/disk error gagal tertutup 503; kuota habis 429 dengan Retry-After.

Fixed window bisa menerima burst di sekitar pergantian menit. Limiter ini belum menggantikan perlindungan DDoS/ingress, admission job, ownership job, atau kuota download. Di belakang reverse proxy, peer akan terlihat sebagai proxy sampai ada desain trusted proxy yang ditinjau; jangan mengaktifkan trust semua forwarded headers.

## Image dan Docker staging internal

Image `clipora-web:v8-staging` memakai base lokal `clipora-worker:v8-dns` yang identitasnya diverifikasi oleh build_image.py. Tambahan Uvicorn/click/h11 dipin dengan SHA-256. Build context hanya daftar file web eksplisit dan wheel terverifikasi, tanpa direktori backend penuh. Build berjalan `--network=none`, pip `--no-index --require-hashes`. Wheel berasal dari PyPI/pip cache; aplikasi dan worker tidak diberi egress untuk mengambil dependensi.

```
.venv/bin/python -B clipora_v8_web/build_image.py /absolute/wheelhouse
.venv/bin/python -B clipora_v8_web/run_staging_test.py /absolute/report.json
docker compose -f clipora_v8_web/staging.compose.yaml up -d --no-build --pull never
```

Compose tersebut khusus pengujian runtime internal, **tidak menyediakan port browser host**. Pengujian port localhost yang diteruskan langsung ke network internal gagal pada Docker Desktop ini walaupun server sehat; port mapping dihapus. Gunakan launcher lokal untuk preview browser. Harness menguji HTTP lewat loopback container dengan docker exec, lalu membersihkan resource disposable miliknya.

Runtime container non-root, readonly, cap-drop ALL, NoNewPrivs, CPU/memory/PID dibatasi, tanpa bind mount/Docker socket. Jaringan internal; DNS upstream dikonfigurasi loopback. State limiter di tmpfs 4 MiB sehingga hilang ketika container dibuat ulang. Image staging masih mewarisi paket worker yang tidak diperlukan web; image web produksi yang minimal, inventaris OS, vulnerability scan, dan lock seluruh transitive dependencies masih menjadi pekerjaan release.

Jangan menyimpulkan staging Docker dapat menerima trafik publik atau bahwa persistent rate limit lintas restart sudah siap dari tes ini. Tes membuktikan runtime Linux web, kebijakan HTTP, serta pembatasan antarproses lokal. Untuk release diperlukan ingress TLS dan penyimpanan state yang dipilih dan diuji.


Kontrak kepemilikan job/file kandidat dijelaskan di [OWNERSHIP.md](OWNERSHIP.md). Entrypoint default dan download publik tetap nonaktif.
