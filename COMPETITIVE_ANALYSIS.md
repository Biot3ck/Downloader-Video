# Analisis kompetitif: Clipora vs SnapTik

Diperbarui: 17 Oktober 2026

Dokumen ini menjawab satu pertanyaan: **apa artinya "menyaingi snaptik.app" secara konkret, dan
bagian mana dari [ROADMAP.md](ROADMAP.md) yang harus berubah karena itu.**

## 1. Ringkasan eksekutif

SnapTik bukan sekadar situs downloader. Ia adalah **mesin SEO berumur 6,5 tahun** dengan ±37–42
juta kunjungan per bulan, 24 bahasa, dan model bisnis iklan. Anda tidak akan menang dengan membuat
downloader yang "lebih bagus" — kode bukan moat mereka, distribusi yang jadi moat.

Tiga temuan yang mengubah strategi:

1. **Indonesia adalah pasar terbesar mereka** (28% dari trafik pencarian, ±2,3 juta kunjungan/bulan).
   Anda berada di pasar yang sama, dengan keunggulan bahasa dan konteks lokal.
2. **Mereka hanya TikTok.** Roadmap Anda merencanakan 4 platform. Itu bukan kelemahan — itu
   diferensiasi yang bisa dipakai, asalkan dikerjakan setelah TikTok terbukti, bukan sebelum.
3. **Trafik mereka tidak stabil.** Organic turun 42,82% month-on-month pada September 2026.
   Peringkat di kategori ini bergeser; pintunya tidak tertutup rapat.

Kesimpulan: menyaingi SnapTik dalam 12 bulan bukan soal menyalip 41 juta kunjungan. Ini soal
mengambil **100–500 ribu kunjungan/bulan** di ceruk yang mereka layani dengan buruk — dan itu
sudah cukup untuk menghasilkan uang.

## 2. Data pasar (September–Oktober 2026)

| Situs | Kunjungan/bulan | Fokus | Catatan |
| --- | ---: | --- | --- |
| ssstik.io | ±110 juta | TikTok | Pemimpin pasar sebenarnya, bukan SnapTik |
| snaptik.app | ±37–42 juta | TikTok | Umur domain 6,5 tahun, otoritas 77 |
| tiktokio.com | ±10 juta | TikTok | Bounce rate rendah (48%) |
| savetik.co | ±4,4 juta | TikTok | |
| ttsave.app | ±265 ribu | TikTok | Trafik turun 12% |

Komposisi trafik SnapTik: **Direct 52%, Google 40%**. Artinya separuh pengguna datang langsung
karena ingat nama — modal brand yang tidak bisa ditiru dengan iklan murah.

Kata kunci utama mereka: `download tiktok` (13,6 juta volume), `download video tiktok` (16,6 juta),
`save tiktok` (1 juta). Ini istilah kepala (head terms) yang didominasi pemain lama. **Jangan
bertarung di sini pada tahun pertama.**

## 3. Apa yang sebenarnya mereka jual

Membaca halaman mereka memberi gambaran yang lebih jujur daripada klaim pemasarannya:

| Elemen | Pengamatan | Arti |
| --- | --- | --- |
| 24 bahasa | Termasuk Jawa, Melayu, Thailand, Vietnam | SEO internasional agresif, bukan lokalisasi mendalam |
| "Preparing HD download… 5s" | Delay buatan sebelum unduhan | Memberi waktu iklan tampil; pengguna dipaksa menunggu |
| "Download Server 01" | Banyak server unduhan | Arsitektur proxy/CDN sendiri (`rapidcdn.app`), bukan tautan CDN langsung |
| Slideshow → MP4 | Gambar + musik digabung jadi video | Fitur pembeda nyata, dan paling sering dicari |
| Download All (ZIP) | Unduh seluruh slide sekaligus | Fitur yang jarang ada di pesaing |
| Aplikasi iOS/Android | "SnapTik: Bookmark Any Video" | Nama samar untuk lolos review App Store |
| Iklan di mana-mana | AdSense + jaringan lain | Satu-satunya sumber pendapatan |
| Tanpa akun, tanpa history | Tidak ada login | Sederhana, tapi tidak ada retensi |

**Temuan teknis paling penting:** mereka mem-proxy media lewat CDN sendiri. Tautan CDN TikTok
punya masa berlaku pendek dan kadang menolak permintaan tanpa header/geo yang tepat. Kalau Clipora
hanya menyerahkan URL CDN langsung ke browser, sebagian unduhan akan gagal. Ini memengaruhi
arsitektur dan biaya — lihat bagian 7.

## 4. Kelemahan yang bisa dieksploitasi

| Kelemahan | Peluang Anda |
| --- | --- |
| **Hanya TikTok** | Multi-platform (TikTok + IG + Pinterest + YouTube) adalah alasan nyata untuk berpindah |
| **Iklan berat + delay buatan** | UX bersih dan cepat adalah pembeda yang langsung terasa, bukan klaim |
| **Tanpa riwayat/akun** | Riwayat lokal + unduh ulang memberi alasan kembali |
| **Tidak transparan soal legalitas** | Halaman kepatuhan yang jujur membangun kepercayaan, terutama untuk pengguna profesional |
| **Lokalisasi dangkal** | Bahasa Indonesia yang benar (bukan hasil terjemahan mesin) + konteks lokal |
| **Tidak ada mode batch terkontrol** | Untuk kreator/agensi, ekspor beberapa aset sekaligus adalah kebutuhan nyata |
| **Tidak ada jaminan kualitas** | Tampilkan resolusi, bitrate, dan ukuran sebelum mengunduh |

## 5. Di mana Anda tidak bisa menang (dan tidak perlu mencoba)

- **Head terms SEO.** `download tiktok` dikuasai domain berumur 6+ tahun dengan otoritas 77.
  Butuh 2–3 tahun dan anggaran backlink untuk menembusnya.
- **Volume.** 41 juta kunjungan/bulan butuh infrastruktur bernilai puluhan ribu dolar per bulan.
- **Kecepatan rilis fitur TikTok.** Mereka punya tim yang memantau perubahan API setiap hari.
- **Brand recall.** Orang mengetik "snaptik" karena sudah tahu. Anda mulai dari nol.

## 6. Strategi yang masuk akal: menang di ceruk, bukan di kepala

### 6.1 Posisi

**"Downloader multi-platform untuk kreator Indonesia."** Bukan "downloader TikTok tercepat" —
itu perang yang sudah selesai.

### 6.2 Tiga wedge

1. **Multi-platform dalam satu tempat.** TikTok, Instagram, Pinterest, YouTube. SnapTik hanya
   menangani satu. Ini satu-satunya alasan struktural untuk berpindah.
2. **Kecepatan dan kejujuran.** Tanpa delay buatan, tanpa popup, tampilkan ukuran file dan
   resolusi sebelum mengunduh, dan katakan terus terang bila versi tanpa watermark tidak tersedia.
3. **Indonesia-first.** Bahasa Indonesia yang wajar, halaman bantuan lokal, dan pemahaman konteks
   (mis. tren TikTok Indonesia, bukan terjemahan konten global).

### 6.3 Kata kunci yang realistis

Jangan `download tiktok`. Kejar ekor panjang (long tail) yang punya niat jelas dan kompetisi rendah:

- `cara download video tiktok tanpa watermark di iphone`
- `download foto slide tiktok jadi video`
- `download reels instagram tanpa watermark`
- `cara simpan video pinterest ke galeri`
- `download video tiktok hd 1080p`
- `aplikasi download video tiktok tanpa watermark android`

Satu halaman per intent, bukan satu halaman untuk semua. Ini persis yang dilakukan SnapTik dengan
`/tiktok-notes-downloader`, `/download-tiktok-slide`, `/download-story-tiktok` — tapi mereka
melewatkan seluruh kategori di luar TikTok.

## 7. Dampak langsung ke arsitektur dan roadmap

### 7.1 Media harus di-proxy, bukan diserahkan sebagai tautan CDN

| Pendekatan | Kelebihan | Kekurangan |
| --- | --- | --- |
| Serahkan URL CDN langsung | Nol biaya bandwidth | Sering gagal (expiry, geo, header), tidak bisa dihitung, tidak bisa di-cache |
| **Proxy lewat server sendiri** | Andal, bisa dihitung, bisa di-cache, bisa diberi nama file | **Bandwidth jadi biaya utama** |

Ini mengubah Fase 3 dan model biaya di roadmap. Konsekuensinya:

- Butuh CDN atau setidaknya cache di depan worker.
- Butuh batas ukuran per unduhan dan kuota harian per IP.
- Biaya bandwidth menjadi variabel yang harus dipantau sejak hari pertama, bukan nanti.

### 7.2 Fitur TikTok yang wajib ada sejak versi pertama

Berdasarkan apa yang paling dicari di pasar:

1. Video tanpa watermark (bila stream tersedia)
2. **Slideshow → MP4** (gambar + musik digabung) — fitur pembeda SnapTik
3. **Download All (ZIP)** untuk slideshow
4. MP3
5. Story dan Notes (opsional, setelah inti stabil)

Tanpa nomor 2 dan 3, Anda kalah di fitur yang paling sering dicari untuk TikTok.

> **Keputusan 17 Oktober 2026:** MP3 dipertahankan sebagai format di halaman Video, bukan
> halaman Audio terpisah. Halaman Audio dan History diputuskan keluar dari scope.

### 7.3 Roadmap butuh alur kerja distribusi yang sekarang tidak ada

Roadmap saat ini 100% engineering. Padahal moat SnapTik adalah SEO, dan SEO adalah pekerjaan
terpisah yang butuh berminggu-minggu:

- Riset kata kunci per platform dan per intent
- Satu halaman pendaratan per intent (bukan satu halaman)
- Halaman "cara pakai" dengan tangkapan layar, per perangkat
- Kecepatan halaman (Core Web Vitals) sebagai syarat peringkat
- Data terstruktur (FAQPage, HowTo, SoftwareApplication)
- Backlink dari forum/kreator Indonesia
- `sitemap.xml`, `robots.txt`, `hreflang` bila multi-bahasa

## 8. Target realistis

| Waktu | Kunjungan/bulan | Yang harus benar |
| --- | ---: | --- |
| Bulan 3 | 0–500 | Produk jalan, belum ada distribusi |
| Bulan 6 | 2.000–10.000 | 20–30 halaman intent terindeks, TikTok + 1 platform lain stabil |
| Bulan 12 | 50.000–150.000 | 4 platform, 100+ halaman, peringkat 1–3 untuk 50+ kata kunci ekor panjang |
| Bulan 24 | 300.000–800.000 | Brand mulai dicari langsung, backlink tumbuh |

Angka ini bukan janji. Ini rentang yang wajar bila eksekusi konsisten; bisa jauh lebih rendah bila
platform memblokir atau halaman tidak terindeks.

Pembanding yang menyehatkan: `ttsave.app` hanya 265 ribu kunjungan/bulan setelah 5 tahun. Itu
bukan kegagalan — itu realitas kategori ini.

## 9. Model bisnis: iklan, dan kenapa itu sulit

SnapTik hidup dari iklan. Anda akan menghadapi dua kendala:

1. **AdSense sering menolak situs downloader.** Kebijakan kontennya ketat. Alternatif: Ezoic,
   PropellerAds, atau jaringan regional — dengan pendapatan per 1.000 tayangan jauh lebih rendah.
2. **Pendapatan iklan tidak menutup bandwidth pada skala kecil.** Pada 100 ribu kunjungan/bulan
   dengan 2 unduhan per pengunjung dan rata-rata 12 MB, itu ±2,4 TB/bulan.

| Skenario | Kunjungan/bulan | Estimasi pendapatan iklan | Estimasi biaya bandwidth | Margin |
| --- | ---: | ---: | ---: | --- |
| Awal | 10.000 | $5–20 | $5–15 | ±0 |
| Tumbuh | 100.000 | $80–400 | $30–90 | Positif tipis |
| Skala | 500.000 | $400–2.000 | $150–450 | Positif |

Artinya: **ini bukan bisnis yang menghasilkan uang pada tahun pertama.** Perlakukan sebagai
proyek portofolio/distribusi, bukan sumber penghasilan utama, sampai trafik menembus 300 ribu.

Alternatif yang lebih realistis untuk Anda: **freemium tanpa iklan** — gratis untuk 3 unduhan/hari,
berbayar untuk batch/HD/prioritas. Tapi ini butuh payment gateway dan badan usaha, dan justru
menambah beban kepatuhan. Jangan dikerjakan sebelum ada trafik.

## 10. Perubahan yang harus masuk ke ROADMAP.md

| # | Perubahan | Alasan |
| --- | --- | --- |
| 1 | Tambah **Fase 2.5 — Distribusi & SEO** (4–6 minggu) | Moat kompetitor adalah SEO; tanpa ini produk tidak akan ditemukan |
| 2 | Fase 3 dipersempit: **TikTok dulu sampai matang**, termasuk slideshow→MP4 dan ZIP | Kalah di fitur inti TikTok berarti kalah sebelum mulai |
| 3 | Tambah **media proxy + CDN** ke arsitektur Fase 3 | Tautan CDN langsung tidak andal |
| 4 | Target metrik ditambah: kunjungan/bulan, peringkat kata kunci, Core Web Vitals | "Lulus" harus terukur, bukan perasaan |
| 5 | Biaya bandwidth jadi baris tersendiri dengan rumus MB × unduhan | Ini biaya yang bisa membunuh produk |
| 6 | Posisi produk ditulis eksplisit: multi-platform untuk kreator Indonesia | Menentukan semua keputusan UI dan konten |

## 11. Risiko kompetitif

| Risiko | Kemungkinan | Mitigasi |
| --- | --- | --- |
| SnapTik menambah platform lain | Sedang | Kecepatan eksekusi dan fokus lokal; mereka bergerak lambat karena skala |
| Google menghukum situs downloader | Tinggi | Konten asli, bukan halaman tipis; kecepatan; tanpa cloaking |
| Platform memblokir IP Anda | Tinggi | Egress bervariasi, batas laju, error jujur |
| AdSense menolak | Tinggi | Rencanakan jaringan alternatif sejak awal |
| Biaya bandwidth melebihi pendapatan | Sedang | Kuota, TTL pendek, kompresi, cache |
| Anda berhenti di tengah jalan | **Tinggi** | Fase kecil dengan hasil terlihat tiap 2–3 minggu |

Risiko terbesar bukan SnapTik. Risiko terbesar adalah proyek 30 minggu yang tidak pernah sampai
peluncuran. Karena itu urutan di roadmap harus menghasilkan sesuatu yang bisa dipakai publik
**jauh sebelum** minggu ke-30.

## 12. Rekomendasi urutan yang lebih pendek ke publik

Alih-alih 30 minggu sebelum ada pengguna, pertimbangkan rilis bertahap:

| Rilis | Isi | Prasyarat |
| --- | --- | --- |
| **v0.1 (minggu 4–6)** | TikTok saja, video tanpa watermark, UI bersih, tanpa iklan, dibatasi 50 pengguna | Fase 1 + spike kelayakan |
| **v0.2 (minggu 10–12)** | Slideshow → MP4, ZIP, MP3 | Media proxy |
| **v0.3 (minggu 14–16)** | Pinterest + Instagram | Allowlist diperluas |
| **v0.4 (minggu 18–20)** | Halaman SEO intent, sitemap, 30 halaman | Distribusi |
| **v1.0 (minggu 24+)** | YouTube, riwayat, kepatuhan lengkap | Enam bloker tertutup |

Ini bertentangan dengan prinsip "jangan buka sebelum enam bloker tertutup" — dan itu memang
trade-off yang harus Anda pilih secara sadar. Rilis tertutup 50 orang dengan allowlist 4 domain
punya permukaan risiko yang jauh lebih kecil daripada rilis publik terbuka. Bila Anda memilih
jalur ini, catat sebagai deviasi di [STATUS.md](backend/clipora_v8_web/STATUS.md), bukan diam-diam.
