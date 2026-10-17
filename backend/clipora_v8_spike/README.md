# Spike kelayakan platform (Fase 0.5)

Alat ini menjawab satu pertanyaan sebelum Anda berkomitmen 8 minggu ke Fase 2:

> **Apakah keempat platform benar-benar bisa diekstrak dari IP server, hari ini?**

## Baca ini dulu: IP menentukan segalanya

Platform memblokir berdasarkan reputasi IP, bukan berdasarkan kode Anda. Artinya:

| Tempat menjalankan | IP keluar | Sah untuk keputusan? |
| --- | --- | --- |
| Laptop / container Docker di laptop | IP rumah / ISP Anda | **Tidak.** Hanya memvalidasi toolchain |
| GitHub Actions | IP datacenter Azure (dipakai bersama) | **Sebagian.** Batas bawah, bukan angka final |
| VPS sewaan / free tier cloud | IP datacenter milik Anda | **Ya.** Ini yang menjadi dasar keputusan |

Hasil dari IP rumah akan **lebih optimistis** daripada kenyataan di server. Jangan ambil
keputusan Fase 0.5 dari laptop.

Setiap laporan mencatat IP keluar di baris kedua, dan memberi peringatan bila IP-nya privat
atau tidak terdeteksi. Jadi hasil selalu bisa diatribusikan.

## Tiga jalur

### 1. VPS (jalur yang sah)

```bash
cd backend/clipora_v8_spike

# isi 20 URL publik per platform
$EDITOR urls.txt

# periksa komposisi daftar tanpa jaringan (cepat, tidak butuh VPS)
python -B -m clipora_v8_spike.spike --urls urls.txt --audit-only
# exit 0 = semua platform terisi, exit 2 = masih kurang

# jalankan dari Mac Anda; skrip menyalin alat, memasang Python + yt-dlp di VPS,
# menjalankan spike, lalu menarik hasilnya kembali
./vps_spike.sh root@203.0.113.10
./vps_spike.sh ubuntu@203.0.113.10 --key ~/.ssh/id_ed25519

# 24 jam kemudian, uji ulang hanya yang sebelumnya berhasil
./vps_spike.sh root@203.0.113.10 --recheck
```

Prasyarat di VPS: Debian 12 / Ubuntu 22.04+, akses SSH. Skrip memasang `python3-venv`
sendiri bila perlu dan Anda punya sudo.

### 2. GitHub Actions (gratis, IP datacenter)

Isi `urls.txt`, push, lalu jalankan workflow `spike` manual dari tab Actions. Hasil CSV
dan Markdown tersedia sebagai artifact. Tidak butuh VPS dan tidak butuh kartu kredit.

Anggap hasilnya batas bawah: IP Azure dipakai bersama banyak penyewa, jadi bisa lebih buruk
daripada VPS khusus.

Workflow menerima tiga input opsional:

| Input | Gunanya |
| --- | --- |
| `impersonate` | `chrome` meniru fingerprint TLS browser. **Wajib untuk TikTok dari IP datacenter.** Memasang `curl_cffi`. |
| `extractor_args` | mis. `youtube:player_client=android_vr` untuk menguji satu client YouTube |
| `platform` | batasi ke satu platform; mempercepat eksperimen |

Contoh eksperimen: `impersonate=chrome`, `platform=youtube`,
`extractor_args=youtube:player_client=tv`.

## Hasil yang sudah tercatat

Ringkasan angka ada di [RESULTS.md](RESULTS.md). Laporan mentah per URL (`.md`/`.csv`) sengaja
tidak di-commit karena memuat tautan pihak ketiga; berkas itu tetap ditulis ke `hasil/` saat
spike dijalankan. Yang tersimpan di repo hanya angka dan penyebab kegagalan.

### 3. Container lokal (hanya untuk memastikan alatnya jalan)

```bash
./run.sh --egress     # pastikan container punya internet
./run.sh              # jalankan spike
```

Hasil masuk ke `hasil/`. **Jangan pakai angka dari sini untuk keputusan.**

## Yang dicatat

Per URL: berhasil/gagal, alasan gagal, jenis gagal (`extraction`, `invalid`, atau `image`),
tinggi maksimum, ukuran file, jumlah format kandidat tanpa watermark, jumlah format
ber-watermark, apakah post berupa slideshow, dan durasi eksekusi.

Kolom "format bersih" adalah **petunjuk, bukan bukti**. Nama format bisa berubah antar versi
API. Verifikasi visual tetap perlu: buka file hasil unduhan dan lihat sendiri.

## Kriteria berhenti (ROADMAP bagian 4.3)

Alat mencetak keputusan otomatis di akhir laporan:

| Hasil | Keputusan |
| --- | --- |
| TikTok ≥85% dan minimal satu platform lain ≥70% | Lanjut ke Fase 1–2 seperti rencana |
| TikTok ≥85% tetapi platform lain <50% | Persempit posisi produk ke TikTok + satu platform |
| TikTok <70% | Berhenti dan tinjau ulang model produk |
| Tidak ada data TikTok | Laporan menolak memberi vonis — isi URL TikTok dulu |
| TikTok <10 URL valid | `DATA KURANG` — laporan menolak memberi vonis |

### URL mati tidak dihitung

URL yang sudah dihapus, privat, atau salah ketik (mis. `HTTP Error 404`, `Video unavailable`)
dipisahkan ke bagian **URL tidak bisa diuji** dan **tidak masuk penyebut** success rate.
Tanpa pemisahan ini, satu URL mati bisa menurunkan angka dan memicu vonis `STOP` palsu.
Kalau laporan menyebut `URL mati/privat, tidak dihitung`, ganti URL tersebut dengan URL publik
lain lalu jalankan ulang — jangan menaikkan angka secara manual.

### Post hanya gambar dipisahkan

yt-dlp adalah ekstraktor video. Post yang hanya berisi gambar gagal di ketiga platform,
masing-masing dengan pesan berbeda:

| Platform | Pesan | Arti |
| --- | --- | --- |
| TikTok | `Unsupported URL … /photo/` | extractor hanya menerima `/video/` |
| Instagram | `There is no video in this post` | post gambar atau carousel |
| Pinterest | `No video formats found!` | pin gambar |

Baris seperti ini masuk bagian **Post hanya gambar** dan tidak masuk penyebut success rate
video. Alat ini tetap tidak mengukur jalur gambar: produksi memakai pembaca per platform di
`clipora_v8_web/real_media.py` (TikTok `imagePost`, Instagram carousel, Pinterest
`originals`/`og:image`), yang diuji manual di STATUS, bukan di sini. Jangan mencampur kedua
angka.

### Angka dari IP rumah bukan keputusan

Menjalankan alat ini dari Mac hanya berguna untuk memastikan URL masih hidup dan bentuk
URL-nya benar. Platform membalas berbeda terhadap IP residensial dan IP datacenter, jadi
angka success rate dari rumah tidak boleh dipakai untuk kriteria berhenti.

## Batasan

- Tidak mengunduh media; hanya membaca metadata. Bandwidth hampir nol.
- Tidak menguji kualitas hasil konversi MP3 atau penggabungan slideshow → MP4.
- Tidak menguji unduhan **gambar**: yt-dlp menolak post gambar di ketiga platform (lihat
  bagian "Post hanya gambar"). Kemampuan itu perlu alat uji sendiri.
- Tidak menguji batas laju jangka panjang. Untuk itu, jalankan ulang beberapa kali dalam sehari.
- Tes otomatis (`test_spike.py`) hanya menguji fungsi murni; tidak ada akses jaringan di CI.
- Versi yt-dlp dipin (`2026.08.19`) supaya hasil antar-jalan bisa dibandingkan. Naikkan versi
  secara sadar dan catat di laporan.
