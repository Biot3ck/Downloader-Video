# Kandidat kepemilikan job dan file

Modul baru ini memakai JobStore durable yang sudah ada, dengan state terpisah di subfolder owned-public. Tidak mengubah JobStore offline lama. Field owner pada tabel jobs tetap execution fence; browser_sessions/job_ownership menyimpan otorisasi browser secara terpisah.

## Kontrak

- Token sesi acak 256 bit, hanya HMAC token yang disimpan, berlaku 24 jam; maksimum 1024 sesi. Tidak menyimpan IP dalam tabel ownership. State direktori 0700 dan database 0600; path state dengan symlink ditolak.
- Job 1 jam, ID acak UUID, maksimum empat queued/processing global dan satu per pemilik. Transaksi BEGIN IMMEDIATE membatasi admission lintas proses. Idempotency key sama + URL normalisasi sama mengembalikan job sama; payload berbeda ditolak.
- Claim/finish tetap memakai execution fence dari queue lama. Payload URL hanya diberikan pada runner yang benar, job processing dan sesi/job belum kedaluwarsa. Cancellation queued bekerja; processing menyimpan request durable dan menunggu observer mengonfirmasi stop. Publikasi memeriksa ulang execution fence/cancellation; lihat CANCELLATION.md.
- API hanya mengembalikan ID/status/timestamp; tidak mengembalikan URL, pesan worker, path, atau execution fence. Missing/foreign/expired memakai respons 404 yang sama, termasuk file. Cookie ganda ditolak.
- Cookie HTTPS memakai __Host-clipora-session, Secure, HttpOnly, SameSite=Strict, Path=/, tanpa Domain. Loopback HTTP memakai nama clipora_session untuk pengujian lokal. Origin/Host/body/limiter/CSP dari web boundary tetap berlaku.
- File memanfaatkan PinnedVideoResponse yang ada: nofollow, ukuran maksimum 64 MiB, signature MP4, inode/lock tetap dipegang selama streaming. HEAD/Range bekerja. Nama download tidak berisi input pengguna.
- Sweep bounded hanya menilai nama job UUID.mp4, tidak menyentuh file asing. Processing artifact dipertahankan sampai runner selesai; completed/orphan expired hanya dihapus jika tidak ada stream aktif yang memegang lock. Sweep berjalan ketika sesi baru diminta dan dapat dipanggil housekeeping runtime. Ini bukan jaminan penghapusan tepat pada detik TTL bila tidak ada aktivitas. Retention endpoint tetap menolak unduhan kedaluwarsa.

## Surface dan pengujian

Factory create_owned_app ada di owned_api.py; entrypoint container eksplisit clipora_v8_web.owned_entry:app. Default preview/entrypoint tetap clipora_v8_web.main:app. Keduanya mempertahankan /api/v8/download -> 503. Tidak ada HTTP submission yang dapat mengantrekan URL, worker, Docker socket atau egress baru pada surface ownership ini. Pengisian job hanya dilakukan kode trusted dalam tes; fixture HTTP container mengisi job/file sintetis untuk memeriksa otorisasi dan Range, bukan mengunduh URL tersebut.

51 tes unit web keseluruhan lulus (termasuk 38 ownership/artifact/API/cancellation test). Tes admission lintas enam proses membuktikan empat diterima, dua dibatasi. Kedua entrypoint container diuji readonly/non-root/cap-drop ALL, network internal tanpa published port, state tmpfs 4 MiB, wheel dependency tanpa download, ownership status/file dan Range melalui HTTP. Image baru menyertakan hanya modul web eksplisit serta job_store.py dan artifact_delivery.py; tidak menyertakan router demo/dev/offline atau Docker client.

## Belum selesai untuk publik

Observer cancellation dan atomic publisher tersedia serta diuji; integrasinya dalam scheduler publik belum dipasang. Belum ada strict periodic GC, ingress TLS produksi/trusted proxy, dependency/OS vulnerability sign-off atau public egress. Artifact/state tmpfs hanya pengujian; database max_page_count bukan kuota total WAL/artifact/log host. Token sesi bukan pengganti akun jika kelak diperlukan. Factory ini tidak membuktikan unduhan empat platform, dan tidak membuktikan kesiapan deployment publik. Jangan menandai kesiapan publik berdasarkan kontrak ownership ini.

## Integrasi lokal eksplisit

Preview aktif sekarang memakai create_local_app dari ../clipora_v8_local_workflow/app.py melalui flag --offline-workflow. Surface tersebut menambahkan POST /api/v8/samples yang hanya menerima objek JSON kosong, scheduler satu leader, dan fixture Docker internal. Sesi valid dipakai kembali saat refresh. Pernyataan surface tanpa submission di atas berlaku untuk factory/image web default; launcher lokal merupakan opt-in terpisah. Tidak ada submission URL publik di kedua surface. Lihat ../clipora_v8_local_workflow/README.md untuk batas/recovery.
