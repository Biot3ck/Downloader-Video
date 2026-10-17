# Clipora — job offline persisten, antrean bersama, dan streaming aman

## Perilaku baru

Endpoint real-offline tetap memakai URL dan status JSON yang sama, tetapi menyimpan job di SQLite. Completed/failed dan antrean queued bertahan setelah proses web dimulai ulang. Job processing yang kehilangan runner tidak diulang otomatis: resource miliknya dibersihkan, artifact yang belum diakui dihapus bila tidak dipakai, lalu job ditandai failed dengan pesan interrupted. Antrean berikutnya baru boleh berjalan setelah recovery berhasil.

Batas untuk satu instalasi dengan direktori state yang sama: maksimum 4 job queued+processing, **1 runner aktif**, dan 256 record tersimpan. Antrean penuh memberi 429; staging penuh memberi 507. Batas ini berlaku lintas proses web pada host lokal yang sama, bukan lintas host/NFS atau seluruh endpoint eksperimen.

## Penyimpanan dan eksekusi

State default: backend/clipora_v8_runtime/jobs.sqlite3 dan runner.lock. Direktori dibuat dengan mode 0700 dan database/lock dengan mode 0600. Tidak ada pembuatan state saat import; inisialisasi terjadi ketika endpoint/state diperlukan atau scheduler offline mulai. SQLite menggunakan WAL, synchronous FULL, transaksi BEGIN IMMEDIATE, parameter SQL terikat, dan koneksi pendek per operasi. Tidak ada dependensi baru.

Scheduler mengikuti lifespan router FastAPI dan hanya berjalan ketika CLIPORA_V8_OFFLINE_BROWSER_TEST=1. Semua proses bersaing untuk satu flock. SQLite memilih job FIFO; owner token mencegah update hasil oleh pemilik lama. Child runner mewarisi fd lock sehingga kematian proses web tidak segera membolehkan worker pengganti saat child masih berjalan. Lock dilepas melalui close, bukan LOCK_UN pada fd yang mungkin masih dipakai child.

Label Docker baru: clipora.offline.owner=clipora-v8-verified-offline dan clipora.offline.job=<job UUID>. Recovery memfilter sekaligus memeriksa label sebelum menghapus container/network. Resource tanpa label atau milik job lain tidak dihapus. Bila daemon/recovery gagal, job tetap processing dan antrean pengganti tidak dimulai; error tercatat pada log scheduler. Ini sengaja gagal tertutup, bukan klaim pemulihan otomatis untuk setiap kegagalan Docker.

Runner menerima artifact tag yang telah dicadangkan di database. Hasil yang tidak cocok dengan tag atau marker TLS ditolak. Staging yang dipakai runner diberikan dari konfigurasi internal server, bukan parameter HTTP. Docker tetap memakai image lokal, jaringan internal, root read-only, capabilities dibuang, dan workspace tmpfs terbatas.

## Pengiriman dan cleanup

PinnedVideoResponse membuka file dengan O_NOFOLLOW, memeriksa inode regular, ukuran, dan signature, lalu memegang flock shared sepanjang respons. FileResponse Starlette membaca melalui fd pseudo-path inode yang telah dibuka; Content-Length, Range/suffix range, HEAD, dan error range tetap dipertahankan. Ekstensi pathsend tidak dipakai untuk fd pseudo-path.

Cleanup membuka inode yang sama dan memerlukan flock exclusive nonblocking. Jika sedang diunduh, file dan record expired dipertahankan untuk percobaan cleanup berikutnya. Permintaan baru setelah TTL tetap 404, tetapi respons yang sudah dimulai boleh selesai. Setelah respons selesai/dibatalkan, fd ditutup dan cleanup boleh menghapus file. Penggantian nama/path setelah file dibuka tidak mengalihkan respons ke file lain.

TTL tetap 15 menit sejak status terminal diperbarui. File orphan lama dengan nama fixture yang valid tetap mengikuti TTL dan lock yang sama. Job queued/processing tidak dihapus karena TTL.

## Bukti pengujian

- 32 tes paket TLS/kontrak/durable queue/staging/delivery lulus di host.
- 25 tes DNS/relay dan 8 tes API v8 lulus. Total **65 tes unit/API**.
- Tujuh tes delivery diulang dalam container Linux network none/read-only: seluruhnya lulus. Ini memverifikasi jalur /proc/self/fd, Range, pembatalan, serta expiry saat streaming, selain jalur /dev/fd di macOS.
- Dua proses Python nyata bersaing pada admission limit yang sama: hanya satu job diterima pada batas satu. Tes lain memastikan child mempertahankan global flock setelah fd parent ditutup dan owner lama tidak dapat menyelesaikan job.
- Job Compose nyata dari aplikasi FastAPI selesai dengan SQLite dan staging temporary yang terisolasi. File tetap identik dengan fixture; proses Python baru dapat membaca completed dari database; setelah lifecycle web dibuka ulang, status dan Range 206 tetap bekerja. Ini bukan pengujian SIGKILL penuh terhadap server aktif.
- Uji recovery Docker membuat dua kelompok container/network disposable dengan job label berbeda. Kelompok interrupted dibersihkan sebelum job penerus diambil; kelompok job lain tetap ada. Job penerus pada tes ownership ini memakai executor pengganti; eksekusi Compose nyata dibuktikan oleh tes end-to-end terpisah.
- Delapan kasus TLS/redirect Docker tetap lulus setelah penambahan label: valid, wrong-host, untrusted-ca, redirect-safe/private/other-host/http/loop.
- Tidak ada container/network berlabel uji tersisa. Lima container lama tetap berjalan.
- V7 dan seluruh dependensi sumber lamanya tetap identik. Perbedaan terhadap snapshot awal tetap hanya main_v8.py, routes.py, dan tiga modul staging dari tahapan sebelumnya. File baru dilacak oleh manifest tahap ini.

## Cakupan dan batas

Perubahan hanya memindahkan endpoint real-offline ke job store baru. Demo jobs, local-mp4, dan offline-e2e lama pada /dev masih merupakan prototipe in-memory dan memiliki batas sendiri. Jangan menganggap batas satu worker meliputi endpoint tersebut.

File lock dan SQLite harus berada pada filesystem lokal yang mendukung semantik locking ini. Belum diuji untuk NFS, multi-host, kehilangan daya, disk penuh, atau daemon Docker yang crash saat recovery. Tidak ada retry otomatis job processing yang terputus, sehingga pengguna perlu membuat sampel baru setelah job ditandai failed.

Scheduler dan download belum memiliki autentikasi/rate limit produksi; server tetap localhost. Audit publik tetap 26/32, NOT READY. Public download tetap 503, tidak ada perubahan VPS/deployment atau pembukaan egress.

## Menjalankan

Hentikan/drain job offline versi lama sebelum restart v8. Jangan campur proses versi lama yang masih memakai dictionary dengan proses versi baru pada instalasi yang sama. Tidak ada migrasi dari dictionary lama yang sudah hilang; metadata persistent baru dipakai untuk job baru.

```sh
CLIPORA_V8_OFFLINE_BROWSER_TEST=1 CLIPORA_V8_USE_COMPOSE=1 .venv/bin/python -B -m uvicorn clipora_v8_fastapi_mvp.main_v8:app --host 127.0.0.1 --port 8088
```

Gunakan server itu melalui /app. Proses web milik pengguna tidak di-restart oleh perubahan ini. Semua QA menggunakan direktori temporary; tidak ada database pengguna yang diekspor atau dihapus. Jangan memasukkan runtime SQLite/WAL/lock ke repository sumber atau membagikannya sebagai artefak publik.

Tes lokal tanpa Docker:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_verified_tls -p 'test*.py' -v
```

End-to-end Docker terisolasi:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_verified_tls/run_durable_e2e.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_verified_tls/run_recovery_e2e.py
```

## Rollback

Arsip clipora-durable-jobs-before.zip berisi empat sumber sebelum perubahan ini, dengan path relatif backend. Drain/hentikan job terlebih dahulu, lalu pulihkan sumber dan restart v8. File baru dapat dibiarkan; sumber lama tidak mereferensikannya. Jangan hapus database/runtime atau staging saat rollback: versi lama tidak membaca SQLite dan tidak dapat mempertahankan status/URL job baru di dictionary. Simpan state untuk forward recovery. Rollback bukan migrasi data otomatis.

## Berikutnya

Uji gangguan proses/daemon dan beban berkelanjutan yang lebih lengkap, minimalkan mount sumber worker, lalu siapkan kebijakan firewall/domain produksi yang dapat ditinjau. Aktivasi publik tetap memerlukan penyelesaian blocker keamanan serta persetujuan deployment terpisah.
