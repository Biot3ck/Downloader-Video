# Roadmap Clipora — dari demo internal ke produk publik

Diperbarui: 17 Oktober 2026
Status awal: **demo internal**. Gate publik `503`, `ready_for_public_launch: false`, enam bloker
keamanan terbuka. Angka tes dan status bloker terkini tetap di
[STATUS.md](backend/clipora_v8_web/STATUS.md); dokumen ini menjawab pertanyaan **"apa yang harus
dikerjakan, dalam urutan apa, dan kapan boleh disebut publik"**.

**Keputusan pemilik (17 Oktober 2026): Model C — downloader publik generik**, untuk TikTok,
Instagram, YouTube dan Pinterest, video tanpa watermark dan gambar. Hosting dimulai dari opsi
gratis. Konsekuensi dan mitigasinya ada di bagian 3.2–3.3; realitas teknis per platform di
bagian 3.5.

## 1. Ringkasan

| Fase | Durasi (paruh waktu) | Hasil | Gate keluar |
| --- | --- | --- | --- |
| 0. Keputusan model & legal | 1–2 minggu | Model C dipilih, ToS/Privasi/Abuse draft | Dokumen keputusan ditandatangani |
| 1. Fondasi operasional (gratis) | 2–3 minggu | VM Linux lokal + domain, TLS, observability, backup | `preflight.py` PASS |
| 2. Enam bloker keamanan | 6–8 minggu | Firewall, allowlist, DNS binding, TLS, kuota, capability | Bukti per bloker di host staging |
| 3. Pipeline unduhan nyata | 5–7 minggu | API job, queue, worker, artifact, delivery, 4 platform | Unduhan nyata 4 platform lulus |
| 4. Fitur produk | 4–5 minggu | Preview+caption nyata, HD/MP3, gambar/album, History, Audio | Semua menu berfungsi |
| 5. Kepatuhan & abuse | 3–4 minggu | Rate limit, takedown, privasi, registrasi PSE | Review kepatuhan lulus |
| 6. Beta → publik | 4–6 minggu | Beta tertutup, load test, security review, launch | Sign-off pemilik |

**Total realistis: 25–32 minggu paruh waktu (±6–8 bulan) atau 15–19 minggu penuh waktu.**
Angka ini mengasumsikan satu pengembang dan tidak menghitung waktu tunggu review eksternal.
Jalur hosting gratis menambah ±1 minggu dibanding VPS langsung, tetapi menghemat ±$100–180
selama tiga bulan pertama.

Urutan ini tidak boleh dibalik. Fase 3 dan 4 mengerjakan fitur yang terlihat pengguna; Fase 2
mengerjakan hal yang mencegah server Anda dipakai sebagai proxy terbuka, titik masuk SSRF, atau
sumber tagihan bandwidth tak terbatas. Membalik urutannya berarti membangun fitur di atas fondasi
yang belum terbukti.

## 2. Kondisi hari ini: aset vs celah

Repo sudah berisi lebih banyak dari yang terlihat di UI. Yang penting adalah mana yang **dipakai
produk** dan mana yang masih **kandidat offline**.

| Komponen | Kondisi | Dipakai produk? | Celah |
| --- | --- | --- | --- |
| UI empat menu + preview + demo download | Jalan, 253 tes | Ya (loopback) | Preview memakai sampel, bukan metadata nyata |
| `POST /api/v8/download` | Sengaja `503` | Tidak | Belum ada implementasi |
| Queue durable + artifact delivery | Ada, teruji offline | Tidak | Belum tersambung ke API publik |
| Ownership/session + Range/HEAD | Ada, teruji | Tidak | Belum dipasang di jalur publik |
| Worker yt-dlp/FFmpeg (image `v8-dns`) | Ada, teruji lewat mTLS fixture | Tidak | Butuh egress nyata + allowlist |
| Pemilihan sumber tanpa watermark TikTok | yt-dlp memilih stream `play_addr` yang memang tanpa watermark | Tidak | Perlu verifikasi per tipe post + fallback bila tidak ada |
| Ekstraktor gambar Pinterest/Instagram | Belum ada | Tidak | Butuh extractor carousel/gambar sendiri |
| `clipora_v8_formats_lab` (HD/MP3) | Kandidat, 8 tes | Tidak | Belum diimpor aplikasi |
| `clipora_v8_image_backend` (album/ZIP) | Ada, 17 tes | Tidak | Belum ada extractor carousel platform |
| Egress stage (DNS/IP policy, parser) | Kandidat, 25 tes | Tidak | Allowlist CDN platform belum ada |
| Three-tier kernel/mTLS | Fixture, 46+35 tes | Tidak | Belum di host nyata |
| Preflight host Linux | 8 tes | Tidak | **BLOCKED** di macOS — belum ada host |
| Image web | Mewarisi FFmpeg/yt-dlp | Ya | Harus dipisah ke runtime minimal |
| Patch OS (expat, jpeg-xl, xz) | Tertunda | — | Wajib sebelum publik |

Kesimpulan jujur: **bahan sudah ada, sambungan belum.** Sebagian besar pekerjaan Fase 3 adalah
menyambungkan modul yang sudah teruji, bukan menulis ulang.

## 3. Gate 0 — Keputusan model produk dan legal

Ini gate paling keras dan paling sering diabaikan. Tidak ada pekerjaan engineering publik yang
boleh dimulai sebelum bagian ini selesai, karena jawabannya mengubah arsitektur, biaya, dan
risiko.

### 3.1 Keputusan pemilik

**Model C — downloader publik generik.** Siapa pun dapat menempel link TikTok, Instagram,
YouTube atau Pinterest, lalu mengunduh video (tanpa watermark bila platform menyediakan sumber
tanpa watermark) dan gambar. Gratis, tanpa akun pada tahap awal.

Keputusan ini dicatat di sini dan menjadi dasar seluruh fase berikutnya. Bila berubah, dokumen
ini harus diperbarui sebelum pekerjaan lain dilanjutkan.

### 3.2 Konsekuensi yang diterima (jujur)

Model C bukan pilihan yang aman. Yang Anda terima dengan memilihnya:

| Konsekuensi | Penjelasan |
| --- | --- |
| Melanggar ToS platform | YouTube, TikTok, Instagram dan Pinterest membatasi pengunduhan/penyalinan otomatis. Ini pelanggaran kontrak, bukan pidana, tetapi cukup untuk memutus akses. |
| Risiko hak cipta | Unduhan untuk penggunaan pribadi punya ruang yang lebih sempit daripada yang dipercaya banyak orang. Bila layanan dipakai untuk membajak konten berhak cipta secara massal, tanggung jawab dapat mengarah ke operator. |
| Pemblokiran sewaktu-waktu | Platform dapat memblokir IP/ASN, mengirim somasi, atau mengubah proteksi. Domain dan hosting dapat memutus layanan setelah ada keluhan. |
| Pemblokiran ISP di Indonesia | Bila dilaporkan, layanan dapat masuk daftar blokir. Registrasi PSE (Kominfo) relevan untuk layanan publik. |
| Payment gateway menolak | Bila nanti dimonetisasi, banyak gateway menolak kategori ini. |
| Tidak bisa masuk App Store | Kebijakan Apple/Google menolak downloader media pihak ketiga. |
| YouTube paling rapuh | Dari IP datacenter, YouTube sering membalas `403`/bot check. Ini akan menjadi platform dengan tingkat kegagalan tertinggi. |

Kesimpulan: produk **bisa** dijalankan, tetapi harus dianggap sebagai layanan berisiko tinggi
dengan kemungkinan mati mendadak. Roadmap ini menambahkan mitigasi agar risikonya terkelola,
bukan hilang.

### 3.3 Mitigasi wajib (tidak opsional)

Semua butir ini harus ada sebelum gate publik dibuka:

1. **Tolak konten privat/login/DRM/paywall.** Hanya konten yang dapat diakses publik tanpa akun.
2. **Atestasi pengguna.** Sebelum mengunduh, pengguna menyatakan berhak atau mendapat izin atas
   konten tersebut. Ini bukan perisai hukum, tetapi membentuk pola penggunaan yang wajar.
3. **Takedown yang benar-benar bekerja.** Halaman publik, email, SLA 3 hari kerja, blocklist URL
   yang dilaporkan, dan log keputusan.
4. **Tanpa penyimpanan jangka panjang.** URL dan file dihapus setelah TTL (mis. 60 menit); log
   tidak menyimpan URL lengkap.
5. **Tanpa batch/bulk dan tanpa API terbuka.** Satu URL per permintaan, rate limit per IP dan
   global, batas ukuran/durasi.
6. **Tanpa monetisasi sampai ada review hukum.** Gratis lebih dulu; bila berbayar, perlu badan
   usaha dan konsultan.
7. **Bahasa pemasaran yang jujur.** Posisikan sebagai alat menyimpan konten untuk dilihat offline
   oleh pemilik/berhak, bukan "bypass" atau "curi".
8. **Kill switch teruji.** Gate `503` harus bisa diaktifkan dalam hitungan detik tanpa deploy.

### 3.4 Deliverables dan kriteria keluar Gate 0

1. **Dokumen keputusan** satu halaman (bagian 3.1 sudah menjadi catatan awal).
2. **Terms of Service** dan **Privacy Policy** (Indonesia + Inggris): batas penggunaan, larangan
   pelanggaran hak cipta, retensi file, penghapusan data.
3. **Kebijakan Abuse & Takedown**: email, SLA, format laporan, prosedur, log.
4. **Daftar platform final** dan penolakan di kode untuk platform di luar daftar.
5. **Keputusan monetisasi**: gratis pada fase ini.

Kriteria keluar: ToS/Privasi/Abuse dapat dibuka publik, daftar platform ditegakkan kode, dan
delapan mitigasi di 3.3 punya pemilik yang jelas.

### 3.5 Realitas teknis per platform dan arti "tanpa watermark"

Penting agar ekspektasi produk sesuai kemampuan teknis:

| Platform | Konten | Watermark | Kesulitan dari VPS | Catatan |
| --- | --- | --- | --- | --- |
| TikTok | Video, carousel foto, audio | **Bisa tanpa watermark** dengan memilih stream `play_addr` yang platform sediakan tanpa watermark | Sedang | Signature/anti-bot sering berubah; sebagian post hanya menyediakan versi ber-watermark |
| Instagram | Reels, post, carousel | Umumnya tanpa watermark kecuali sumbernya sudah ber-watermark | Sedang–tinggi | Banyak login wall dan rate limit; carousel butuh extractor sendiri |
| YouTube | Video, Shorts | Tidak ada watermark | **Tinggi** | IP datacenter sering kena `403`/bot check; butuh PO token/cookie; kegagalan intermiten |
| Pinterest | Gambar, video pin, idea pin | Umumnya tanpa watermark | Rendah–sedang | Gambar mudah; video butuh ekstraksi terpisah |

**"Tanpa watermark" berarti memilih sumber yang platform sediakan tanpa watermark, bukan
menghapus watermark dari piksel video.** Bila hanya versi ber-watermark yang tersedia, produk
harus mengatakannya dengan jujur — bukan memalsukan hasil. Menghapus watermark dari piksel
(inpainting) tetap non-goal karena merusak kualitas dan menambah risiko hukum.

Untuk gambar, yang dibutuhkan bukan "hapus watermark" tetapi ekstraksi galeri: resolusi asli,
urutan slide, dan ZIP untuk carousel. Pinterest dan carousel Instagram adalah dua sumber utama.

## 4. Fase 1 — Fondasi operasional (2–3 minggu, jalur gratis)

Tanpa host Linux nyata, enam bloker tidak mungkin ditutup. Karena anggaran belum tersedia,
fase ini memakai jalur gratis lebih dulu, lalu bermigrasi ke VPS saat siap.

### 4.1 Jalur gratis yang disarankan

| Opsi | Biaya | Cocok untuk | Batasan |
| --- | --- | --- | --- |
| **VM Linux lokal** (UTM/QEMU/Lima di macOS) | Gratis | Membuktikan firewall, DNS binding, TLS, kuota, capability, preflight | Bukan host publik; tidak membuktikan perilaku jaringan internet nyata |
| Oracle Cloud Free Tier (ARM) | Gratis | Uji egress nyata dan allowlist CDN | Kapasitas sering penuh; kebijakan dapat berubah; IP datacenter mudah diblokir platform |
| Hetzner/Contabo VPS kecil | ±$5–8/bulan | Staging publik murah | Bukan gratis, tetapi paling dekat dengan produksi |

**Rekomendasi:** mulai dengan VM lokal untuk menutup lima dari enam bloker (semua kecuali
allowlist CDN nyata), lalu pindah ke VPS termurah saat pipeline butuh internet nyata. Ini
menghindari membayar server sebelum ada yang bisa dijalankan di atasnya.

Peringatan: banyak free tier melarang beban kerja pengunduh media berintensitas bandwidth
tinggi. Baca ToS penyedia sebelum mengandalkannya; jangan jadikan free tier sebagai host produksi.

### 4.2 Pekerjaan

| Pekerjaan | Detail | Bukti |
| --- | --- | --- |
| Provision host | VM Debian 13 (agar cocok `base_image.lock`), 4 vCPU / 8 GB / 60 GB; IPv4 dan IPv6 | `uname -a`, spesifikasi |
| DNS & domain | A + AAAA ke host staging, TTL rendah, tanpa wildcard | `dig` A/AAAA |
| TLS | Let's Encrypt via ACME untuk domain staging; self-signed tidak dihitung bukti | `openssl s_client`, masa berlaku |
| Hardening dasar | SSH key-only, non-root, nftables default-deny, unattended-upgrades | `ss -tulpn`, ruleset |
| Observability | Log terstruktur tanpa URL/secret, metrik CPU/disk/request/job, alert disk >80% | Dashboard + 1 alert teruji |
| Backup & restore | Backup harian DB + konfigurasi, **uji restore** | Log restore drill |
| CI/CD | Build image di CI, tag immutable, rollback satu perintah | Deploy + rollback teruji |
| Preflight | `clipora_v8_staging_linux/preflight.py` di host | Laporan `PASS`, bukan `BLOCKED` |

**Kriteria keluar:** preflight PASS, situs HTTPS menjawab `200` dengan gate masih `503`, restore
dan rollback sudah pernah dilakukan sekali.

## 5. Fase 2 — Menutup enam bloker keamanan (6–8 minggu)

Setiap bloker butuh bukti di host staging, bukan di laptop. Ini pekerjaan paling berat dan paling
tidak terlihat oleh pengguna.

| # | Bloker | Pekerjaan konkret | Bukti penutupan |
| --- | --- | --- | --- |
| 1 | Firewall konfigurasi produksi | Terapkan ruleset dari `clipora_v8_firewall_candidate` di host nyata: inbound hanya 80/443 (+SSH terbatas), outbound default-deny kecuali ke gateway egress, IPv4 **dan** IPv6 | `nft list ruleset` + uji peer TCP nyata ditolak/diterima |
| 2 | Allowlist publik independen | Perluas `destination_policy.py`: host platform + CDN resmi (`*.googlevideo.com`, `*.tiktokcdn.com`, `*.cdninstagram.com`, `*.pinimg.com`), validasi **setiap** hop redirect, tolak private/link-local/metadata (`169.254.169.254`), tolak DNS rebinding lewat IP pinning | Tabel kasus uji: 20+ URL jahat ditolak, 4 platform diterima |
| 3 | Binding DNS → IP/socket/firewall | Satu resolusi per job, snapshot A+AAAA lengkap, IP yang divalidasi **sama** dengan IP socket dan rule firewall; uji expiry, revoke, concurrency, crash controller | Log korelasi IP untuk 100 job berturut-turut |
| 4 | TLS jalur produksi | TLS aplikasi dengan identitas produksi; worker→gateway→egress mTLS; rotasi & revocation; tolak downgrade dan redirect lintas domain | Uji negatif: CA salah, hostname salah, sertifikat kedaluwarsa |
| 5 | Kuota total & sustained load | Kuota byte **dan** inode di level host (project quota/bind mount) mencakup media, temp, DB/WAL, log; uji ENOSPC, restart, cancel saat streaming | Load test 30 menit + simulasi disk penuh |
| 6 | Capability & controller failure | Container tanpa CAP, rootfs readonly, non-root, seccomp; controller mati → fail closed (job gagal, bukan lanjut) | `capsh --print` di dalam container + uji kill controller |

Tambahan yang harus ikut di fase ini:

- **Pisahkan image web dari image worker.** Sekarang web membawa FFmpeg/yt-dlp/codec. Runtime web
  minimal mengurangi permukaan serangan dan ukuran image.
- **Terapkan patch OS tertunda:** expat, jpeg-xl, xz, plus triage 156 record "open review required"
  dan 4 "undetermined" di [docs/OS_PACKAGE_REVIEW.md](backend/clipora_v8_web/docs/OS_PACKAGE_REVIEW.md).
- **Pin & inventaris dependency**, termasuk salinan expat milik Python.

**Kriteria keluar:** enam baris di atas punya bukti yang bisa ditunjukkan, dan `STATUS.md` diperbarui
dari "6 terbuka" menjadi "0 terbuka" — hanya setelah bukti ada, bukan sebelum.

## 6. Fase 3 — Pipeline unduhan nyata (5–6 minggu)

Ini fase yang mengubah produk dari "mengenali link" menjadi "benar-benar mengunduh".

### 6.1 API publik

| Endpoint | Perilaku |
| --- | --- |
| `POST /api/v8/download` | `202` + `job_id`, idempotency key, batas ukuran/durasi, validasi platform |
| `GET /api/v8/jobs/{id}` | Status: `queued`, `running`, `done`, `failed`, `cancelled` + progres |
| `GET /api/v8/jobs/{id}/file` | Stream artifact, dukung `Range`/`HEAD`, nama file aman |
| `DELETE /api/v8/jobs/{id}` | Batalkan job antre atau hentikan yang berjalan |
| `GET /api/v8/metadata` | Title, caption, thumbnail, durasi, uploader — untuk preview nyata |

### 6.2 Komponen yang disambungkan

1. **Scheduler**: queue durable dari `clipora_v8_browser_real_mp4` + worker pool dengan
   backpressure dan batas konkurensi per IP.
2. **Worker**: yt-dlp + FFmpeg di container `network: none`, hanya lewat gateway egress.
3. **Ownership**: sesi anonim bertanda tangan, job terikat pemilik, identifier sulit ditebak.
4. **Artifact**: TTL (mis. 60 menit), GC terjadwal, kuota, penghapusan saat kedaluwarsa.
5. **Error taxonomy**: pesan aman ke pengguna, detail sensitif hanya di log internal.

### 6.3 Urutan yang disarankan

1. **TikTok** lebih dulu: jalur penuh paling cepat terbukti, dan sumber tanpa watermark tersedia
   lewat pemilihan format.
2. **Pinterest** kedua: ekstraksi gambar paling sederhana, memberi fitur "download gambar" lebih
   awal.
3. **Instagram** ketiga: butuh penanganan login wall, rate limit, dan carousel.
4. **YouTube** terakhir: paling rapuh dari IP datacenter. Jangan jadikan YouTube penentu
   keberhasilan fase ini; siapkan pesan kegagalan yang jujur bila bot check muncul.
5. Setelah keempatnya stabil, integrasikan HD/MP3 dan album/ZIP.

### 6.4 Kriteria keluar

- Unduhan nyata berhasil dari UI untuk **keempat platform**, dengan success rate terukur dan
  dilaporkan apa adanya (termasuk kegagalan YouTube bila ada).
- Video TikTok keluar tanpa watermark bila sumber tanpa watermark tersedia; bila tidak, UI
  menyatakan versi yang tersedia.
- Gambar Pinterest dan carousel Instagram terunduh dengan resolusi asli dan urutan benar.
- Cancel, retry, refresh halaman, dan file kedaluwarsa berperilaku benar.
- Tidak ada URL pengguna di log; tidak ada akses jaringan dari web tier.

## 7. Fase 4 — Fitur produk (4–5 minggu)

| Fitur | Status sekarang | Pekerjaan |
| --- | --- | --- |
| Preview + caption nyata | Sampel statis | Ambil metadata dari worker, tampilkan sebelum unduh, dengan fallback bila metadata gagal |
| Pemilih sumber tanpa watermark | Belum ada | Tampilkan opsi "tanpa watermark" hanya bila stream tersedia; jelaskan bila tidak |
| Video HD | Kandidat | Integrasikan `clipora_v8_formats_lab`, tampilkan ukuran/bitrate, jelaskan bila HD tidak tersedia |
| MP3 | Kandidat | Konversi via FFmpeg, tampilkan bitrate, batasi durasi |
| Gambar & album | Backend ada, extractor belum | Extractor Pinterest, carousel TikTok/IG, ZIP, urutan gambar, batas jumlah |
| Progres unduhan | Belum ada | SSE atau polling; tampilkan tahap (fetch → convert → siap) |
| History | Placeholder `Soon` | Daftar job per sesi, status file, tombol unduh ulang, hapus |
| Audio | Placeholder `Soon` | Halaman khusus audio, memakai pipeline MP3 |
| Aksesibilitas & mobile | Baik, perlu audit | Audit keyboard, screen reader, kontras, 320px |

**Kriteria keluar:** empat menu berfungsi tanpa label `Soon`, dan tidak ada elemen UI yang
menjanjikan fitur yang belum ada.

## 8. Fase 5 — Kepatuhan, abuse, privasi (3–4 minggu)

| Pekerjaan | Detail |
| --- | --- |
| Rate limit berlapis | Per IP, per sesi, dan global; 429 dengan pesan jelas; batas harian |
| Anti-abuse | Deteksi pola scraping, batas konkurensi, opsi captcha saat lonjakan |
| Takedown | Email publik, formulir laporan, prosedur hapus, log keputusan, SLA |
| Privasi | Data minimization, retensi log, tidak menyimpan URL lebih lama dari perlu, hapus atas permintaan |
| Registrasi PSE | Pendaftaran Penyelenggara Sistem Elektronik (Kominfo) bila layanan publik — konfirmasi kewajibannya dengan konsultan hukum |
| Konten terlarang | Tolak konten privat/login/DRM; kebijakan tegas untuk konten ilegal; jalur eskalasi |
| Halaman publik | ToS, Privacy, Abuse, Status, Kontak — dapat diakses tanpa JS |

**Kriteria keluar:** halaman kepatuhan live, rate limit teruji di bawah beban, dan ada satu
simulasi laporan takedown end-to-end.

## 9. Fase 6 — Beta dan peluncuran (4–6 minggu)

1. **Beta tertutup** 20–50 pengguna, undangan, feedback terstruktur, metrik: success rate,
   latency, error per platform, biaya per unduhan.
2. **Load test** pada kapasitas target (mis. 50 unduhan bersamaan), ukur titik putus.
3. **Chaos test**: worker mati, disk penuh, DNS gagal, platform menolak, restart di tengah job.
4. **Security review** eksternal (opsional tetapi disarankan) atau minimal checklist OWASP ASVS L1.
5. **Launch checklist**: domain, TLS, backup teruji, alert aktif, runbook, rollback, kontak.
6. **Peluncuran bertahap**: 5% → 25% → 100% trafik, dengan tombol matikan (gate `503`) yang
   terbukti bekerja.

**Kriteria keluar:** gate publik baru diubah menjadi `true` setelah semua bukti di atas
dikumpulkan. Gate tidak boleh diubah dengan mengganti konstanta.

## 10. Jadwal usulan

```
Minggu   1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29 30 31 32
Gate 0  ██ ██
Fase 1     ██ ██ ██
Fase 2           ██ ██ ██ ██ ██ ██ ██ ██
Fase 3                       ██ ██ ██ ██ ██ ██ ██
Fase 4                                ██ ██ ██ ██ ██
Fase 5                                     ██ ██ ██ ██
Fase 6                                           ██ ██ ██ ██ ██ ██
```

Fase 2 dan 3 sengaja tumpang tindih: sebagian pekerjaan pipeline bisa dimulai setelah firewall
dan allowlist dasar berdiri. Fase 5 dimulai lebih awal bila takedown sudah dibutuhkan sebelum
beta.

## 11. Biaya operasional (perkiraan)

| Pos | Bulan 1–3 (jalur gratis) | Saat publik | Saat tumbuh |
| --- | --- | --- | --- |
| Host | $0 (VM lokal / free tier) | $25–45 | $80–160 |
| Domain | $1/bulan | $1/bulan | $1/bulan |
| Bandwidth/egress | $0 | Termasuk | $20–100 (tergantung volume) |
| Object storage (opsional) | $0 | $0–5 | $10–40 |
| Monitoring/uptime | $0 (self-host) | $0 | $0–20 |
| Email transaksional | $0 | $0–10 | $10–30 |
| **Total** | **±$1/bulan** | **±$30–60/bulan** | **±$120–350/bulan** |

Biaya terbesar yang sering dilupakan bukan server, tetapi **bandwidth video** dan **waktu
memelihara extractor**. yt-dlp perlu diperbarui saat platform berubah; anggarkan beberapa jam
per bulan untuk itu, selamanya. Pada model C, tambahkan juga biaya antisipasi: domain cadangan,
email takedown, dan waktu menangani keluhan.

## 12. Risiko utama

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Platform memblokir server | Unduhan gagal massal | Rotasi egress, batas laju, deteksi dini, jalur error yang jujur |
| YouTube menolak IP datacenter (`403`/bot check) | Fitur YouTube tidak stabil | Jangan janjikan 100%; fallback pesan jelas, opsi cookie/PO token hanya untuk konten yang diizinkan |
| yt-dlp rusak setelah update platform | Fitur inti mati | Pin versi, tes harian, update terkontrol, alert success rate |
| Takedown/somasi/blokir ISP | Layanan tidak bisa diakses | Mitigasi 3.3, kebijakan takedown, kepatuhan PSE, kill switch |
| Harapan "watermark hilang total" tidak terpenuhi | Pengguna kecewa | UI menyatakan sumber yang tersedia; tidak memalsukan hasil |
| Free tier melarang beban kerja ini | Host dimatikan mendadak | Baca ToS penyedia; free tier hanya untuk staging, bukan produksi |
| Penyalahgunaan (proxy terbuka, konten ilegal) | Server disalahgunakan | Allowlist ketat, rate limit, moderasi, log audit |
| Disk penuh | Semua job gagal | Kuota inode+byte, GC, alert 80% |
| Biaya bandwidth meledak | Tagihan tak terduga | Batas ukuran/durasi, TTL pendek, kuota harian |
| Bus factor satu orang | Proyek berhenti | Dokumentasi runbook, CI, backup, akses darurat |

## 13. Non-goals (sengaja tidak dikerjakan)

- Menghapus watermark dari piksel video (inpainting). Yang dikerjakan adalah memilih sumber tanpa
  watermark yang platform sediakan.
- Konten privat, login-only, DRM, atau paywall.
- Bypass paywall, region lock, atau rate limit platform.
- Menjanjikan kualitas "original" di luar yang disediakan sumber.
- Aplikasi mobile native pada fase ini.

## 14. Cara memakai dokumen ini

1. Gate 0 sudah diputuskan (Model C, bagian 3.1); lengkapi deliverables di bagian 3.4 sebelum
   membuka gate publik.
2. Kerjakan fase secara berurutan; jangan mulai Fase 3 sebelum Fase 2 punya bukti.
3. Setiap akhir fase, perbarui [STATUS.md](backend/clipora_v8_web/STATUS.md): angka tes, status
   bloker, dan deviasi yang diketahui.
4. Gate publik hanya berubah bila kriteria keluar Fase 6 terpenuhi dan buktinya bisa ditunjukkan.
5. Bila ada pekerjaan di luar urutan ini, catat sebagai deviasi — jangan diam-diam.
6. Bila keputusan model berubah (mis. pindah ke Model B karena tekanan hukum), perbarui bagian
   3.1 dan tinjau ulang Fase 5–6 sebelum melanjutkan.

Dokumen pendukung: [RELEASE_SECURITY.md](backend/clipora_v8_web/docs/RELEASE_SECURITY.md),
[MVP_READINESS.md](backend/clipora_v8_web/docs/MVP_READINESS.md),
[OS_PACKAGE_REVIEW.md](backend/clipora_v8_web/docs/OS_PACKAGE_REVIEW.md),
[ARCHITECTURE.md](backend/clipora_v8_web/ARCHITECTURE.md).
