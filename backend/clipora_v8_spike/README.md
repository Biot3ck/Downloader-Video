# Spike kelayakan platform (Fase 0.5)

Alat ini menjawab satu pertanyaan sebelum Anda berkomitmen 8 minggu ke Fase 2:

> **Apakah keempat platform benar-benar bisa diekstrak dari IP server, hari ini?**

Jalankan di **host yang akan dipakai produksi** (VPS, bukan laptop), karena yang diuji adalah
perilaku platform terhadap IP tersebut. Hasil dari laptop hanya baseline.

## Cara pakai

```bash
cd backend

# 1. isi daftar URL
$EDITOR clipora_v8_spike/urls.txt

# 2. jalankan
.venv/bin/python -B -m clipora_v8_spike.spike \
    --urls clipora_v8_spike/urls.txt \
    --out hasil-spike.csv

# 3. 24 jam kemudian, uji ulang yang sebelumnya berhasil
.venv/bin/python -B -m clipora_v8_spike.spike \
    --urls clipora_v8_spike/urls.txt \
    --out hasil-spike-24jam.csv \
    --recheck hasil-spike.csv
```

Hasil: `hasil-spike.csv` (data mentah) dan `hasil-spike.md` (tabel + keputusan otomatis).

## Yang dicatat

Per URL: berhasil/gagal, alasan gagal, tinggi maksimum, ukuran file, jumlah format kandidat
tanpa watermark, jumlah format ber-watermark, apakah post berupa slideshow, dan durasi eksekusi.

Kolom "format bersih" adalah **petunjuk, bukan bukti**. Nama format bisa berubah antar versi
API. Verifikasi visual tetap perlu: buka file hasil unduhan dan lihat sendiri.

## Kriteria berhenti (ROADMAP bagian 4.3)

Alat mencetak keputusan otomatis di akhir laporan:

| Hasil | Keputusan |
| --- | --- |
| TikTok ≥85% dan minimal satu platform lain ≥70% | Lanjut ke Fase 1–2 seperti rencana |
| TikTok ≥85% tetapi platform lain <50% | Persempit posisi produk ke TikTok + satu platform |
| TikTok <70% | Berhenti dan tinjau ulang model produk |

## Batasan

- Tidak mengunduh media; hanya membaca metadata. Bandwidth hampir nol.
- Tidak menguji kualitas hasil konversi MP3 atau penggabungan slideshow → MP4.
- Tidak menguji batas laju jangka panjang. Untuk itu, jalankan ulang beberapa kali dalam sehari.
- Tes otomatis (`test_spike.py`) hanya menguji fungsi murni; tidak ada akses jaringan di CI.
