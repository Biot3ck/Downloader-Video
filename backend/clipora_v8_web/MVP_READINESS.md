# Rencana release Clipora MVP

Status review terbaru: [RELEASE_SECURITY.md](RELEASE_SECURITY.md). Pemeriksaan lokal dan hardening storage admission sudah dilakukan; keamanan publik belum disetujui. Linux staging terpisah belum tersedia, VM tetap tidak dipasang, unduhan publik tetap nonaktif. Bagian milestone di bawah adalah riwayat perkembangan; UI produk saat ini memakai empat menu tanpa file picker/sampel, dengan preferensi Video/HD/MP3 yang belum aktif.

Target pengguna: unduhan video publik YouTube, TikTok, Instagram, dan Pinterest. Model hybrid: browser menangani preview/save lokal; backend menangani ekstraksi metadata, pemilihan media, dan merge bila dibutuhkan. Tidak menjanjikan akses browser langsung ke CDN sebelum CORS, expiry URL, dan ketergantungan cookie/header diuji. Tidak menjanjikan penghapusan watermark dari piksel video. Dukungan video privat/login/DRM bukan bagian kandidat MVP ini.

## Status yang sudah terbukti

- v7 dan sumber alur offline stabil tidak diubah oleh paket staging baru.
- UI staging memakai desain Clipora yang dipulihkan dan empat platform yang diminta. Pengenalan URL dan preview file lokal bekerja. Download URL publik tetap nonaktif.
- API staging tidak memuat endpoint demo/dev/offline. Host/Origin, CSP, batas body/deadline, dan limiter SQLite antarproses tersedia serta diuji.
- Firewall kandidat offline menerima topologi tervalidasi, menerapkan DROP IPv4/IPv6, membatasi satu IP/port, lalu menjalankan layanan tanpa capability. Penolakan koneksi dan percobaan perubahan firewall dibuktikan dengan peer TCP nyata pada namespace Linux disposable.
- Image web staging terpisah berhasil dibangun dari base lokal yang diverifikasi, ditambah wheel dengan hash terpin. Runtime readonly/non-root/cap-drop, state tmpfs, dan HTTP internal diuji. Browser memakai launcher loopback karena published port pada network internal Docker Desktop tidak berhasil.
- Job MP4 offline lama tetap selesai melalui Compose; artifact identik dan Range HTTP tetap bekerja.

## Pekerjaan yang wajib selesai sebelum unduhan publik

| Urutan | Deliverable | Kriteria selesai |
| --- | --- | --- |
| 1 | Integrasi broker tujuan dan firewall | DNS A+AAAA divalidasi lengkap, hostname input dan CDN/redirect diberi izin eksplisit, IP yang divalidasi sama dengan IP socket/rule firewall. Tidak ada resolve kedua. Lease, concurrency, expiry, cancellation, dan kegagalan update policy diuji. |
| 2 | Jalur TLS kandidat produksi | Worker → gateway → egress → fixture HTTPS bekerja dengan konfigurasi kandidat yang sama; salah CA/hostname, redirect private/lintas domain, downgrade, dan loop ditolak. Fixture tiga tier/mTLS sudah terhubung; kesetaraan konfigurasi produksi dan kebijakan redirect/CDN publik masih harus dibuktikan. |
| 3 | Job publik dengan ownership | URL tervalidasi masuk antrean durable; job/file terikat sesi pemilik, identifier sulit ditebak, idempotency, batas ukuran/durasi/waktu, pembatalan, retensi, dan respons kegagalan aman. Router real-offline lama tidak boleh langsung dipublikasikan. |
| 4 | Penyimpanan dan beban | Kuota filesystem staging host mencakup media, file sementara, DB/WAL/log; sustained load, disk penuh, restart, crash, job duplikat, serta cleanup saat streaming lulus. Kuota tmpfs worker dan limiter bukan pengganti kuota staging host. |
| 5 | Staging Linux dan ingress | Lingkungan Linux terpisah dengan isolasi setara produksi, TLS ingress, trusted-proxy yang sempit, persistent state, health/readiness, log tanpa URL/secret, metrik, backup/restore dan rollback. Belum ada VM Linux terpisah dalam sesi ini; VPS produksi tidak disentuh. |
| 6 | Verifikasi empat platform | Setelah gate egress dipenuhi dan aktivasi pengujian disetujui: uji nyata video publik yang diizinkan untuk tiap platform, link pendek/redirect, audio-video terpisah, ukuran/durasi, throttling, error platform, dan playback browser/mobile. Pengenalan hostname bukan bukti extractor berfungsi. |
| 7 | Review release | Image web minimal, seluruh dependency/OS dipin dan diinventarisasi, vulnerability review, smoke browser/mobile, accessibility, kebijakan penggunaan/privasi yang disetujui pemilik, dan runbook incident. |
| 8 | Persetujuan aktivasi/deployment | Tunjukkan hasil tes, konfigurasi final, perubahan VPS yang spesifik, domain/TLS, kapasitas dan rollback. Minta persetujuan final sebelum mengaktifkan internet atau deployment. |

Audit lama tetap 26/32 dengan enam blocker. Jangan mengganti gate False menjadi True statis; penutupan harus memiliki bukti kandidat yang terintegrasi dan dapat direproduksi. Preview yang hidup pada localhost bukan launch publik.


## Pembaruan persiapan kode 17 Oktober 2026

- Kandidat offline kini menguji worker aktual melalui dua Docker network internal, gateway/egress TLS mutual, DNS/broker/kernel/socket/TLS aplikasi. Bypass selama lease aktif dan penolakan identitas client TLS diuji. Lihat ../clipora_v8_firewall_candidate/THREE_TIER_KERNEL.md dan MUTUAL_TLS.md. Ini bukan bukti unduhan internet atau attestation host Linux deployment.
- Kandidat ownership memakai queue durable yang ada, sesi browser, idempotency, authorization status/file/Range, queued cancellation dan bounded sweep dengan inode lock. Factory container eksplisit tersedia dan diuji; submission publik/scheduler tetap belum dipasang. Lihat OWNERSHIP.md.
- VM Linux tidak dipasang: pemilik memilih melanjutkan persiapan kode tanpa VM. Usulan ../clipora_v8_staging_linux/PROPOSAL.md tetap dokumen rencana, bukan persetujuan instalasi. VPS dan deployment tidak disentuh.
- Audit lama tetap 26/32. Tidak ada hardcoded gate yang diganti berdasarkan pengujian fixture. Lima, QEMU, Colima atau VM baru tidak dipasang oleh pekerjaan ini.

- Kandidat kini mempunyai request cancellation durable, observer stop, dan atomic publisher yang menolak hasil terlambat. Cancellation worker Docker aktual diuji pada tiga tier/mTLS saat lease aktif. Lihat CANCELLATION.md; ini belum memasang scheduler/download publik.

## Alur produk lokal yang sudah tersambung

Launcher eksplisit `run_local.py --offline-workflow` kini menyediakan UI → sesi browser → antrean durable → worker Docker aktual → gateway/egress mTLS → MP4 → preview/unduh. Sampel tetap berasal dari jaringan internal, tidak menerima URL pengguna. Progres, cancel aktif, refresh, ownership/Range dan recovery setelah SIGKILL diuji. Lihat ../clipora_v8_local_workflow/README.md.

Preview aktif memakai mode lokal ini. Default image web tidak menyertakan launcher/Docker client dan sampel tetap nonaktif. Scheduler publik, unduhan empat platform, staging Linux terpisah, kuota filesystem host, beban dan sign-off release belum selesai. Enam blocker audit tetap terbuka; langkah berikutnya bergantung pada lingkungan staging yang disetujui, bukan menambah demo offline.

## Preflight staging yang dapat dijalankan

Paket ../clipora_v8_staging_linux/preflight.py memeriksa kelayakan awal host secara read-only dan menolak macOS/Docker Desktop sebagai bukti host Linux terpisah. Endpoint Docker jarak jauh tidak dihubungi; report tidak memuat endpoint/nama host/environment. Delapan tes kontrak lulus. Hasil pada komputer ini tetap blocked sesuai kondisi sebenarnya. Lihat ../clipora_v8_staging_linux/README.md untuk urutan suite dan matriks bukti enam blocker. Tidak ada provisioning atau aktivasi otomatis.

## Penambahan scope gambar

Pemilik meminta foto TikTok/Instagram/Pinterest. UI mempunyai mode Images / album, kontrak validasi media_kind, serta preview/unduh per gambar dan ZIP dari file perangkat. Lihat IMAGES.md. Extractor foto platform dan artifact album publik belum diimplementasikan; gate keamanan dan kriteria staging tetap berlaku. Tidak ada perubahan worker MP4/v7 atau aktivasi egress.

## Pipeline album offline tersambung

Kandidat clipora_v8_image_backend kini memakai worker Docker network none untuk decode PNG/JPEG/WebP, manifest berurutan/hash, atomic publish, ownership/read route gambar dan ZIP, Range/HEAD, TTL/cancel/GC bersama video. Launcher lokal menyediakan sample album fixed; public URL tetap ditolak. Uji pembatalan image worker aktual dilanjutkan sukses worker MP4 aktual. Browser memulihkan hasil album setelah refresh. 17 tes backend gambar, 57 tes web dan enam workflow lokal lulus. Lihat ../clipora_v8_image_backend/README.md. Ini belum mengimplementasikan extractor/carousel platform publik atau menutup gate staging/egress.

## Perubahan UI atas permintaan pemilik

Fitur On your device / No upload, pemilih file video/gambar, preview perangkat dan ZIP browser dihapus. Pilihan Video/Images, pengenalan link, sampel backend, ownership dan galeri/ZIP hasil backend tetap dipertahankan. Tidak ada aktivasi egress atau perubahan v7.

## Restrukturisasi frontend produk

Empat menu Video/Photo/Audio/History tersedia. Hanya pengenalan link video/foto yang tersambung pada produk; Audio/History unavailable karena belum ada API yang sesuai. Semua demo/sampel dipindahkan ke /dev loopback-only dan kode perangkat disimpan sebagai arsip Tools yang tidak disajikan. Lihat UI_RESTRUCTURE.md untuk checkpoint Git, pengujian 16 kombinasi viewport/view, dan batas integrasi. Public gate dan enam blocker tidak berubah.
