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

**Posisi kompetitif (17 Oktober 2026): menyaingi snaptik.app.** Posisi yang dipilih bukan
"downloader TikTok tercepat" — itu perang yang sudah selesai dan dimenangkan domain berumur 6,5
tahun dengan ±41 juta kunjungan/bulan. Posisi yang dipilih: **downloader multi-platform untuk
kreator Indonesia**, dengan kecepatan, kejujuran, dan UX bersih sebagai pembeda. Analisis lengkap
pasar, kelemahan kompetitor, target trafik, dan model bisnis ada di
[COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md).

## 1. Ringkasan

| Fase | Durasi (paruh waktu) | Hasil | Gate keluar |
| --- | --- | --- | --- |
| 0. Keputusan model & legal | 1–2 minggu | Model C dipilih, ToS/Privasi/Abuse draft | Dokumen keputusan ditandatangani |
| 0.5. Spike kelayakan platform | 1 minggu | 4 platform diuji dari IP VPS, success rate mentah | Angka nyata, bukan asumsi |
| 1. Fondasi operasional (gratis) | 2–3 minggu | VM Linux lokal + domain, TLS, observability, backup | `preflight.py` PASS |
| 2. Enam bloker keamanan | 6–8 minggu | Firewall, allowlist, DNS binding, TLS, kuota, capability | Bukti per bloker di host staging |
| 2.5. Distribusi & SEO | 4–6 minggu | 30+ halaman intent, sitemap, Core Web Vitals | Terindeks dan mulai menerima kunjungan |
| 3. Pipeline unduhan nyata | 5–7 minggu | API job, queue, worker, proxy media, TikTok matang | TikTok ≥90% success rate |
| 4. Fitur produk | 4–5 minggu | Slideshow→MP4, ZIP, HD/MP3, gambar/album, History | Semua fitur inti TikTok ada |
| 5. Kepatuhan & abuse | 3–4 minggu | Rate limit, takedown, privasi, registrasi PSE | Review kepatuhan lulus |
| 6. Beta → publik | 4–6 minggu | Beta tertutup, load test, security review, launch | Sign-off pemilik |

**Total realistis: 29–38 minggu paruh waktu (±7–9 bulan) atau 17–22 minggu penuh waktu.**
Angka ini mengasumsikan satu pengembang dan tidak menghitung waktu tunggu review eksternal.
Jalur hosting gratis menambah ±1 minggu dibanding VPS langsung, tetapi menghemat ±$100–180
selama tiga bulan pertama.

Fase 2.5 bisa berjalan paralel dengan Fase 2 oleh orang berbeda (penulis konten), sehingga total
kalender bisa lebih pendek daripada jumlah baris di atas. Bila Anda mengerjakan sendiri, tambahkan
4–6 minggu itu ke total.

Urutan ini tidak boleh dibalik. Fase 3 dan 4 mengerjakan fitur yang terlihat pengguna; Fase 2
mengerjakan hal yang mencegah server Anda dipakai sebagai proxy terbuka, titik masuk SSRF, atau
sumber tagihan bandwidth tak terbatas. Membalik urutannya berarti membangun fitur di atas fondasi
yang belum terbukti.

## 2. Kondisi hari ini: aset vs celah

Repo sudah berisi lebih banyak dari yang terlihat di UI. Yang penting adalah mana yang **dipakai
produk** dan mana yang masih **kandidat offline**.

| Komponen | Kondisi | Dipakai produk? | Celah |
| --- | --- | --- | --- |
| UI empat menu + preview + demo download | Jalan | Ya (loopback) | Preview memakai sampel, bukan metadata nyata |
| `POST /api/v8/download` | Sengaja `503` | Tidak | Belum ada implementasi |
| Queue durable + artifact delivery | Ada, teruji offline | Tidak | Belum tersambung ke API publik |
| Ownership/session + Range/HEAD | Ada, teruji | Tidak | Belum dipasang di jalur publik |
| Worker yt-dlp/FFmpeg (image `v8-dns`) | Ada, teruji lewat mTLS fixture | Tidak | Butuh egress nyata + allowlist |
| Pemilihan sumber tanpa watermark TikTok | Hipotesis: satu format tanpa watermark tersedia | Tidak | **Harus diverifikasi di Fase 0.5**, bukan diasumsikan |
| Ekstraktor gambar Pinterest/Instagram | Belum ada | Tidak | Butuh extractor carousel/gambar sendiri |
| `clipora_v8_formats_lab` (HD/MP3) | Kandidat, teruji | Tidak | Belum diimpor aplikasi |
| `clipora_v8_image_backend` (album/ZIP) | Ada, teruji | Tidak | Belum ada extractor carousel platform |
| Egress stage (DNS/IP policy, parser) | Kandidat, teruji | Tidak | Allowlist CDN platform belum ada |
| Three-tier kernel/mTLS | Fixture, teruji | Tidak | Belum di host nyata |
| Preflight host Linux | Teruji | Tidak | **BLOCKED** di macOS — belum ada host |
| Image web | Mewarisi FFmpeg/yt-dlp | Ya | Harus dipisah ke runtime minimal |
| Patch OS (expat, jpeg-xl, xz) | Tertunda | — | Wajib sebelum publik |

Angka tes per paket tidak diulang di sini; sumber tunggalnya
[STATUS.md](backend/clipora_v8_web/STATUS.md).

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
| TikTok | Video, carousel foto, audio | **Berpotensi tanpa watermark** — platform menyediakan beberapa varian stream; mana yang ber-watermark berubah antar versi API | Sedang | **Hipotesis yang harus diverifikasi di Fase 0.5**, bukan fakta |
| Instagram | Reels, post, carousel | Umumnya tanpa watermark kecuali sumbernya sudah ber-watermark | Sedang–tinggi | Banyak login wall dan rate limit; carousel butuh extractor sendiri |
| YouTube | Video, Shorts | Tidak ada watermark | **Tinggi** | IP datacenter sering kena `403`/bot check; butuh PO token/cookie; kegagalan intermiten |
| Pinterest | Gambar, video pin, idea pin | Umumnya tanpa watermark | Rendah–sedang | Gambar mudah; video butuh ekstraksi terpisah |

**"Tanpa watermark" berarti memilih sumber yang platform sediakan tanpa watermark, bukan
menghapus watermark dari piksel video.** Bila hanya versi ber-watermark yang tersedia, produk
harus mengatakannya dengan jujur — bukan memalsukan hasil. Menghapus watermark dari piksel
(inpainting) tetap non-goal karena merusak kualitas dan menambah risiko hukum.

Untuk gambar, yang dibutuhkan bukan "hapus watermark" tetapi ekstraksi galeri: resolusi asli,
urutan slide, dan ZIP untuk carousel. Pinterest dan carousel Instagram adalah dua sumber utama.

## 4. Fase 0.5 — Spike kelayakan platform (1 minggu)

Fase ini ada karena satu alasan: **risiko terbesar proyek ini adalah asumsi bahwa keempat
platform bisa diekstrak dari IP datacenter**, dan roadmap versi sebelumnya baru mengujinya di
minggu ke-10. Bila asumsi itu salah, delapan minggu Fase 2 terbuang.

### 4.1 Yang dikerjakan

1. VPS termurah (boleh free tier) dengan yt-dlp versi terbaru.
2. 20 URL publik per platform: TikTok (video, slideshow, story), Instagram (reel, post, carousel),
   Pinterest (gambar, video pin), YouTube (video, Shorts).
3. Catat untuk setiap URL: berhasil/gagal, alasan kegagalan, resolusi, ukuran, ada/tidak watermark.
4. Uji ulang 24 jam kemudian untuk melihat apakah tautan CDN masih valid.

### 4.2 Yang dihasilkan

Tabel success rate mentah per platform, tanpa diperbaiki, tanpa dibulatkan. Ini menjadi dasar
angka target di Fase 3.

### 4.3 Kriteria berhenti (penting)

| Hasil spike | Keputusan |
| --- | --- |
| TikTok ≥85% dan minimal satu platform lain ≥70% | Lanjut ke Fase 1–2 seperti rencana |
| TikTok ≥85% tetapi platform lain <50% | Lanjut, tetapi posisi produk dipersempit ke TikTok + satu platform |
| TikTok <70% | **Berhenti dan tinjau ulang.** Pertimbangkan Model B atau alat pribadi |

Menetapkan kriteria berhenti sebelum mulai adalah satu-satunya cara agar keputusan nanti tidak
diambil berdasarkan emosi setelah berbulan-bulan kerja.

## 5. Fase 1 — Fondasi operasional (2–3 minggu, jalur gratis)

Tanpa host Linux nyata, enam bloker tidak mungkin ditutup. Karena anggaran belum tersedia,
fase ini memakai jalur gratis lebih dulu, lalu bermigrasi ke VPS saat siap.

### 5.1 Jalur gratis yang disarankan

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

### 5.2 Pekerjaan

| Pekerjaan | Detail | Bukti |
| --- | --- | --- |
| Provision host | VM Debian 13 (agar cocok `base_image.lock`), 4 vCPU / 8 GB / 60 GB; IPv4 dan IPv6 | `uname -a`, spesifikasi |
| DNS & domain | A + AAAA ke host staging, TTL rendah, tanpa wildcard | `dig` A/AAAA |
| TLS | Jalur VPS: Let's Encrypt via ACME untuk domain staging. Jalur VM lokal: sertifikat self-signed **hanya** untuk menguji konfigurasi — bukan bukti TLS produksi | `openssl s_client`, masa berlaku, dan catatan jalur mana yang dipakai |
| Hardening dasar | SSH key-only, non-root, nftables default-deny, unattended-upgrades | `ss -tulpn`, ruleset |
| Observability | Log terstruktur tanpa URL/secret, metrik CPU/disk/request/job, alert disk >80% | Dashboard + 1 alert teruji |
| Backup & restore | Backup harian DB + konfigurasi, **uji restore** | Log restore drill |
| CI/CD | Build image di CI, tag immutable, rollback satu perintah | Deploy + rollback teruji |
| Preflight | `clipora_v8_staging_linux/preflight.py` di host | Laporan `PASS`, bukan `BLOCKED` |

**Kriteria keluar jalur VM lokal:** preflight PASS, situs HTTPS menjawab `200` (self-signed),
restore dan rollback sudah pernah dilakukan sekali. Lima dari enam bloker bisa dibuktikan di sini.

**Kriteria keluar jalur VPS:** tambahan TLS publik dengan domain nyata, dan allowlist CDN diuji
dengan trafik internet sungguhan.

## 6. Fase 2 — Menutup enam bloker keamanan (6–8 minggu)

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
- **Kill switch runtime.** Saat ini gate publik adalah konstanta hardcoded di `main.py`
  (`public_downloads_enabled: False` pada tiga tempat, plus `503` di `/api/v8/download`). Ganti
  dengan konfigurasi yang dibaca saat runtime, perubahan tercatat di audit log, dan berlaku tanpa
  restart. Bukti: matikan dan nyalakan gate di bawah beban tanpa deploy.

**Kriteria keluar:** enam baris di atas punya bukti yang bisa ditunjukkan, dan `STATUS.md` diperbarui
dari "6 terbuka" menjadi "0 terbuka" — hanya setelah bukti ada, bukan sebelum.

## 7. Fase 2.5 — Distribusi & SEO (4–6 minggu)

Fase ini tidak ada di roadmap versi sebelumnya, dan itu kesalahan. SnapTik tidak menang karena
kodenya; ia menang karena 6,5 tahun halaman terindeks. Produk terbaik tanpa distribusi akan
mendapat nol pengunjung.

### 7.1 Kata kunci yang dikejar

Bukan head term. Fokus pada ekor panjang dengan niat jelas:

| Platform | Contoh intent | Kompetisi |
| --- | --- | --- |
| TikTok | `cara download video tiktok tanpa watermark di iphone` | Sedang |
| TikTok | `download slide tiktok jadi video` | Rendah |
| Instagram | `download reels instagram tanpa watermark` | Sedang |
| Pinterest | `cara simpan video pinterest ke galeri` | Rendah |
| Umum | `download video tiktok hd 1080p` | Sedang–tinggi |

### 7.2 Halaman yang dibangun

1. **Satu halaman per intent**, bukan satu halaman untuk semua. Minimal 30 halaman pada rilis
   pertama.
2. **Halaman "cara pakai"** dengan tangkapan layar per perangkat (Android, iPhone, PC).
3. **Halaman platform**: TikTok, Instagram, Pinterest, YouTube — masing-masing dengan FAQ sendiri.
4. **Halaman pembanding** yang jujur ("Clipora vs SnapTik"), menyebut kelebihan kompetitor juga.
5. **Halaman kepatuhan**: ToS, Privasi, Abuse, Kontak — dapat dibuka tanpa JavaScript.

### 7.3 Syarat teknis SEO

- `sitemap.xml` dan `robots.txt`.
- Data terstruktur `FAQPage`, `HowTo`, `SoftwareApplication`.
- Core Web Vitals: LCP <2,5 detik, CLS <0,1, INP <200 ms.
- URL bersih dan stabil; tanpa parameter sesi di URL publik.
- Tanpa cloaking dan tanpa halaman tipis — Google menghukum kategori ini dengan mudah.

### 7.4 Kriteria keluar

- 30+ halaman terindeks (dicek lewat Search Console, bukan asumsi).
- 10+ kata kunci ekor panjang masuk 100 besar.
- LCP <2,5 detik pada koneksi 4G tersimulasi.
- Satu halaman menerima kunjungan organik pertama.

## 8. Fase 3 — Pipeline unduhan nyata (5–7 minggu)

Ini fase yang mengubah produk dari "mengenali link" menjadi "benar-benar mengunduh".

### 8.1 API publik

| Endpoint | Perilaku |
| --- | --- |
| `POST /api/v8/download` | `202` + `job_id`, idempotency key, batas ukuran/durasi, validasi platform |
| `GET /api/v8/jobs/{id}` | Status: `queued`, `running`, `done`, `failed`, `cancelled` + progres |
| `GET /api/v8/jobs/{id}/file` | Stream artifact, dukung `Range`/`HEAD`, nama file aman |
| `DELETE /api/v8/jobs/{id}` | Batalkan job antre atau hentikan yang berjalan |
| `GET /api/v8/metadata` | Title, caption, thumbnail, durasi, uploader — untuk preview nyata |

### 8.2 Proxy media (keputusan arsitektur penting)

SnapTik tidak menyerahkan tautan CDN TikTok langsung ke browser; ia mem-proxy media lewat CDN
sendiri. Alasannya praktis: tautan CDN TikTok berumur pendek, kadang menolak permintaan tanpa
header/geo yang tepat, dan tidak bisa dihitung.

| Pendekatan | Kelebihan | Kekurangan |
| --- | --- | --- |
| Serahkan URL CDN langsung | Nol biaya bandwidth | Sering gagal, tidak terukur, tidak bisa di-cache |
| **Proxy lewat server sendiri** | Andal, terukur, bisa di-cache, nama file rapi | **Bandwidth jadi biaya utama** |

Keputusan: **proxy**, dengan batas ukuran per unduhan, kuota harian per IP, dan TTL pendek.
Cache di depan worker bila memungkinkan.

### 8.3 Komponen yang disambungkan

1. **Scheduler**: queue durable dari `clipora_v8_browser_real_mp4` + worker pool dengan
   backpressure dan batas konkurensi per IP.
2. **Worker**: yt-dlp + FFmpeg di container `network: none`, hanya lewat gateway egress.
3. **Ownership**: sesi anonim bertanda tangan, job terikat pemilik, identifier sulit ditebak.
4. **Artifact**: TTL (mis. 60 menit), GC terjadwal, kuota, penghapusan saat kedaluwarsa.
5. **Error taxonomy**: pesan aman ke pengguna, detail sensitif hanya di log internal.

### 8.4 Urutan yang disarankan

1. **TikTok sampai matang** — video tanpa watermark, slideshow, story. Ini platform yang paling
   banyak dicari dan yang paling mungkin memberi trafik awal.
2. **Pinterest** kedua: ekstraksi gambar paling sederhana, memberi fitur "download gambar" lebih
   awal.
3. **Instagram** ketiga: butuh penanganan login wall, rate limit, dan carousel.
4. **YouTube** terakhir: paling rapuh dari IP datacenter. Jangan jadikan YouTube penentu
   keberhasilan fase ini.

### 8.5 Target terukur

Angka ini dipakai untuk menilai lulus/tidak, bukan perasaan:

| Platform | Target success rate | Catatan |
| --- | ---: | --- |
| TikTok | ≥90% | Diukur dari 100 URL publik acak |
| Pinterest | ≥95% | Ekstraksi gambar stabil |
| Instagram | ≥80% | Login wall dan rate limit menekan angka |
| YouTube | ≥50% | Realistis dari IP datacenter; laporkan apa adanya |

Tambahan: p95 latensi <30 detik per unduhan, dan biaya bandwidth <$0,005 per unduhan.

### 8.6 Kriteria keluar

- TikTok memenuhi target ≥90% dari 100 URL uji, diukur dan dicatat.
- Video TikTok keluar tanpa watermark bila sumber tanpa watermark tersedia; bila tidak, UI
  menyatakan versi yang tersedia.
- Slideshow TikTok dapat diunduh sebagai gambar (ZIP) dan sebagai MP4.
- Cancel, retry, refresh halaman, dan file kedaluwarsa berperilaku benar.
- Tidak ada URL pengguna di log; tidak ada akses jaringan dari web tier.

## 9. Fase 4 — Fitur produk (4–5 minggu)

| Fitur | Status sekarang | Pekerjaan |
| --- | --- | --- |
| Preview + caption nyata | Sampel statis | Ambil metadata dari worker, tampilkan sebelum unduh, dengan fallback bila metadata gagal |
| Pemilih sumber tanpa watermark | Belum ada | Tampilkan opsi "tanpa watermark" hanya bila stream tersedia; jelaskan bila tidak |
| **Slideshow → MP4** | Belum ada | Gabungkan gambar + musik jadi video; ini fitur yang paling dicari untuk TikTok |
| **Download All (ZIP)** | Belum ada | Unduh seluruh slide sekaligus, urutan benar |
| Video HD | Kandidat | Integrasikan `clipora_v8_formats_lab`, tampilkan ukuran/bitrate, jelaskan bila HD tidak tersedia |
| MP3 | Kandidat | Konversi via FFmpeg, tampilkan bitrate, batasi durasi |
| Gambar & album | Backend ada, extractor belum | Extractor Pinterest, carousel TikTok/IG, ZIP, urutan gambar, batas jumlah |
| Progres unduhan | Belum ada | SSE atau polling; tampilkan tahap (fetch → convert → siap) |
| History | Placeholder `Soon` | Daftar job per sesi, status file, tombol unduh ulang, hapus |
| Audio | Placeholder `Soon` | Halaman khusus audio, memakai pipeline MP3 |
| Aksesibilitas & mobile | Baik, perlu audit | Audit keyboard, screen reader, kontras, 320px |

**Kriteria keluar:** empat menu berfungsi tanpa label `Soon`, dan tidak ada elemen UI yang
menjanjikan fitur yang belum ada.

## 10. Fase 5 — Kepatuhan, abuse, privasi (3–4 minggu)

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

## 11. Fase 6 — Beta dan peluncuran (4–6 minggu)

1. **Beta tertutup** 20–50 pengguna, undangan, feedback terstruktur, metrik: success rate,
   latency, error per platform, biaya per unduhan.
2. **Load test** pada kapasitas target (mis. 50 unduhan bersamaan), ukur titik putus.
3. **Chaos test**: worker mati, disk penuh, DNS gagal, platform menolak, restart di tengah job.
4. **Security review** eksternal (opsional tetapi disarankan) atau minimal checklist OWASP ASVS L1.
5. **Launch checklist**: domain, TLS, backup teruji, alert aktif, runbook, rollback, kontak.
6. **Peluncuran bertahap**: 5% → 25% → 100% trafik, dengan tombol matikan (gate `503`) yang
   terbukti bekerja.

**Kriteria keluar:** gate publik baru diubah menjadi `true` setelah semua bukti di atas
dikumpulkan. Gate tidak boleh diubah dengan mengganti konstanta; ia dibaca dari konfigurasi
runtime yang tercatat di audit log.

### 11.1 Alternatif: rilis bertahap lebih awal

Rencana di atas membuka pintu publik pada minggu 27–32. Itu lambat untuk proyek yang bersaing
dengan pemain mapan. Alternatif yang dipertimbangkan di
[COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) bagian 12:

| Rilis | Isi | Prasyarat |
| --- | --- | --- |
| v0.1 (minggu 4–6) | TikTok saja, 50 pengguna undangan | Fase 0.5 + Fase 1 |
| v0.2 (minggu 10–12) | Slideshow → MP4, ZIP, MP3 | Media proxy |
| v0.3 (minggu 14–16) | Pinterest + Instagram | Allowlist diperluas |
| v0.4 (minggu 18–20) | 30 halaman SEO | Fase 2.5 |
| v1.0 (minggu 24+) | YouTube, riwayat, kepatuhan lengkap | Enam bloker tertutup |

Ini bertentangan dengan prinsip "jangan buka sebelum enam bloker tertutup". Trade-off-nya nyata:
rilis tertutup 50 orang dengan allowlist 4 domain punya permukaan risiko jauh lebih kecil daripada
rilis publik terbuka. Bila Anda memilih jalur ini, catat sebagai deviasi di `STATUS.md` — jangan
diam-diam.

## 12. Jadwal usulan

| Fase | Minggu | Durasi |
| --- | --- | --- |
| Gate 0 — keputusan & legal | 1–2 | 2 minggu |
| Fase 0.5 — spike kelayakan | 3 | 1 minggu |
| Fase 1 — fondasi operasional | 4–6 | 3 minggu |
| Fase 2 — enam bloker keamanan | 7–14 | 8 minggu |
| Fase 2.5 — distribusi & SEO | 10–16 | 4–6 minggu (paralel) |
| Fase 3 — pipeline unduhan | 13–19 | 7 minggu |
| Fase 4 — fitur produk | 20–24 | 5 minggu |
| Fase 5 — kepatuhan & abuse | 23–26 | 4 minggu (paralel) |
| Fase 6 — beta & peluncuran | 27–32 | 6 minggu |

Fase 2.5 dan 5 ditulis sebagai paralel karena sifatnya berbeda (konten dan dokumen) dan bisa
dikerjakan sela-sela pekerjaan teknis. Bila Anda mengerjakan semuanya sendiri tanpa paralelisasi,
tambahkan 4–6 minggu sehingga total menjadi ±36–38 minggu.

## 13. Biaya operasional (perkiraan)

| Pos | Bulan 1–3 (jalur gratis) | Saat publik | Saat tumbuh |
| --- | --- | --- | --- |
| Host | $0 (VM lokal / free tier) | $25–45 | $80–160 |
| Domain | $1/bulan | $1/bulan | $1/bulan |
| Bandwidth/egress | $0 | $10–30 | $150–450 |
| Object storage (opsional) | $0 | $0–5 | $10–40 |
| Monitoring/uptime | $0 (self-host) | $0 | $0–20 |
| Email transaksional | $0 | $0–10 | $10–30 |
| **Total** | **±$1/bulan** | **±$35–90/bulan** | **±$250–700/bulan** |

### 13.1 Cara menghitung bandwidth

Ini baris yang paling sering salah dihitung. Rumusnya:

```
bandwidth_bulanan = unduhan_per_hari × 30 × rata_rata_MB × 1,3
```

Faktor 1,3 memberi ruang untuk retry dan overhead. Contoh pada 1.000 unduhan/hari dengan
rata-rata 12 MB: `1.000 × 30 × 12 MB × 1,3 ≈ 468 GB/bulan`.

| Volume | Rata-rata 12 MB | Perkiraan biaya egress |
| --- | ---: | ---: |
| 100 unduhan/hari | 47 GB/bulan | $0–5 |
| 1.000 unduhan/hari | 468 GB/bulan | $4–9 |
| 10.000 unduhan/hari | 4,7 TB/bulan | $40–90 |
| 50.000 unduhan/hari | 23 TB/bulan | $200–450 |

Karena itu **proxy media** (bagian 8.2) harus disertai batas ukuran dan kuota harian sejak hari
pertama, bukan ditambahkan setelah tagihan datang.

Biaya terbesar yang sering dilupakan bukan server, tetapi **bandwidth video** dan **waktu
memelihara extractor**. yt-dlp perlu diperbarui saat platform berubah; anggarkan beberapa jam
per bulan untuk itu, selamanya.

## 14. Risiko utama

| Risiko | Dampak | Mitigasi |
| --- | --- | --- |
| Platform memblokir server | Unduhan gagal massal | Rotasi egress, batas laju, deteksi dini, jalur error yang jujur |
| YouTube menolak IP datacenter (`403`/bot check) | Fitur YouTube tidak stabil | Jangan janjikan 100%; fallback pesan jelas. **Jangan pakai cookie akun pribadi** — risiko ban akun dan pelanggaran ToS yang lebih berat |
| yt-dlp rusak setelah update platform | Fitur inti mati | Pin versi, tes harian, update terkontrol, alert success rate |
| Takedown/somasi/blokir ISP | Layanan tidak bisa diakses | Mitigasi 3.3, kebijakan takedown, kepatuhan PSE, kill switch |
| Harapan "watermark hilang total" tidak terpenuhi | Pengguna kecewa | UI menyatakan sumber yang tersedia; tidak memalsukan hasil |
| Free tier melarang beban kerja ini | Host dimatikan mendadak | Baca ToS penyedia; free tier hanya untuk staging, bukan produksi |
| Penyalahgunaan (proxy terbuka, konten ilegal) | Server disalahgunakan | Allowlist ketat, rate limit, moderasi, log audit |
| Disk penuh | Semua job gagal | Kuota inode+byte, GC, alert 80% |
| Biaya bandwidth meledak | Tagihan tak terduga | Batas ukuran/durasi, TTL pendek, kuota harian, rumus 13.1 |
| Kalah distribusi dari kompetitor | Nol pengunjung meski produk bagus | Fase 2.5, 30+ halaman intent, ukur lewat Search Console |
| Bus factor satu orang | Proyek berhenti | Dokumentasi runbook, CI, backup, akses darurat |

## 15. Non-goals (sengaja tidak dikerjakan)

- Menghapus watermark dari piksel video (inpainting). Yang dikerjakan adalah memilih sumber tanpa
  watermark yang platform sediakan.
- Konten privat, login-only, DRM, atau paywall.
- Bypass paywall, region lock, atau rate limit platform.
- Menjanjikan kualitas "original" di luar yang disediakan sumber.
- Aplikasi mobile native pada fase ini.
- Bertarung di head term SEO (`download tiktok`) pada tahun pertama.
- Iklan sebagai sumber pendapatan utama sebelum 300 ribu kunjungan/bulan.

## 16. Cara memakai dokumen ini

1. Gate 0 sudah diputuskan (Model C, bagian 3.1); lengkapi deliverables di bagian 3.4 sebelum
   membuka gate publik.
2. Jalankan Fase 0.5 sebelum berkomitmen ke Fase 2. Bila spike gagal, berhenti dan tinjau ulang.
3. Kerjakan fase secara berurutan; jangan mulai Fase 3 sebelum Fase 2 punya bukti.
4. Setiap akhir fase, perbarui [STATUS.md](backend/clipora_v8_web/STATUS.md): angka tes, status
   bloker, dan deviasi yang diketahui.
5. Gate publik hanya berubah bila kriteria keluar Fase 6 terpenuhi dan buktinya bisa ditunjukkan.
6. Bila ada pekerjaan di luar urutan ini, catat sebagai deviasi — jangan diam-diam.
7. Bila keputusan model berubah (mis. pindah ke Model B karena tekanan hukum), perbarui bagian
   3.1 dan tinjau ulang Fase 5–6 sebelum melanjutkan.

Dokumen pendukung: [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md),
[RELEASE_SECURITY.md](backend/clipora_v8_web/docs/RELEASE_SECURITY.md),
[MVP_READINESS.md](backend/clipora_v8_web/docs/MVP_READINESS.md),
[OS_PACKAGE_REVIEW.md](backend/clipora_v8_web/docs/OS_PACKAGE_REVIEW.md),
[ARCHITECTURE.md](backend/clipora_v8_web/ARCHITECTURE.md).
