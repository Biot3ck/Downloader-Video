# Status Clipora v8

Diperbarui: 17 Oktober 2026. **Dokumen ini adalah satu-satunya sumber angka tes dan status
bloker.** Dokumen di [docs/](docs/) adalah catatan audit pada saat penulisannya; bila angkanya
berbeda, yang berlaku adalah angka di sini dan hasil eksekusi tes.

## Ringkasan

| Pertanyaan | Jawaban |
| --- | --- |
| Siap unduhan publik? | **Tidak.** Gate `503`, `ready_for_public_launch: false` |
| Siap demo internal? | **Ya**, dengan state privat dan hanya loopback |
| Fitur aktif | Pengenalan link Video, Photo & Audio; format Video, Video HD, MP3 |
| Fitur belum ada | Ekstraksi/konversi media |
| Bloker publik terbuka | 6 (butuh host staging Linux terpisah) |
| Jalur rilis | Disiplin enam bloker; rilis bertahap/undangan ditolak (17 Okt 2026) |

## Tes

Dijalankan dari direktori `backend` dengan Python 3.15 pada image lokal:

| Paket | Jumlah | Perintah |
| --- | ---: | --- |
| `clipora_v8_web` | 95 | `.venv/bin/python -B -m unittest discover -s clipora_v8_web -p 'test*.py' -q` |
| `clipora_v8_formats_lab` | 8 | idem, ganti direktori |
| `clipora_v8_firewall_candidate` | 46 | idem |
| `clipora_v8_verified_tls` | 35 | idem |
| `clipora_v8_secure_egress_stage` | 25 | idem |
| `clipora_v8_staging_linux` | 8 | idem |
| `clipora_v8_image_backend` | 17 | idem |
| `clipora_v8_local_workflow` | 6 | idem |
| `clipora_v8_spike` | 29 | idem (fungsi murni; tanpa jaringan) |
| JavaScript frontend | 16 | `node clipora_v8_web/test_frontend_async.cjs` |
| **Total** | **285** | |

Tes ini membuktikan perilaku kode pada lingkungan lokal. Tes ini **bukan** pentest dan bukan
bukti kesiapan deployment. Angka 26/32 pada audit legacy adalah check yang sebagian memang
dihardcode belum terbukti, bukan skor.

## Bloker persetujuan publik

Belum ada yang bisa ditutup tanpa host staging Linux terpisah. Pemilik memilih tanpa VM, jadi
status yang jujur adalah **demo internal**, bukan "hampir siap".

| Bloker | Syarat penutupan |
| --- | --- |
| Firewall konfigurasi produksi | Topologi/route IPv4/IPv6 pada kandidat deployment nyata |
| Allowlist publik independen | Kebijakan platform/CDN/redirect eksplisit; bypass DNS/rebinding/private/metadata ditolak lewat jalur kandidat yang sama |
| Binding DNS → IP/socket/firewall | Korelasi di Linux staging: snapshot A+AAAA lengkap, expiry/revoke/concurrency/crash controller |
| TLS jalur produksi | Worker/gateway/egress + TLS aplikasi dengan identitas produksi, rotasi/revocation, redirect/downgrade |
| Kuota total dan sustained load | Byte/inode termasuk DB/WAL/log/temp/artifact; ENOSPC, restart, cancel, streaming di bawah beban |
| Pelepasan capability dan kegagalan controller | Inspeksi runtime proses kandidat, IPC, controller gagal tertutup |

Rincian: [docs/RELEASE_SECURITY.md](docs/RELEASE_SECURITY.md).

## Deviasi yang diketahui

1. **Image web mewarisi image worker.** `clipora-worker:v8-dns` membawa FFmpeg, yt-dlp dan
   library codec; web tier tidak membutuhkannya. Pemisahan ke runtime Python minimal adalah
   perubahan terpisah yang harus diaudit ulang. Pin ada di `base_image.lock`.
2. **History dihapus dari surface; Audio sekarang nyata.** Menu History tidak ada di markup,
   JavaScript, maupun route demo (`/api/v8/history` → `404`). Halaman Audio Downloader sudah
   aktif: input URL video, preview pemutar audio, dan tombol **Download MP3**. Audio memakai
   kontrak pengenalan yang sama dengan video (`media_kind=video`), dengan `media_kind=audio`
   hanya pada endpoint preview demo. Format MP3 juga masih tersedia sebagai pilihan di halaman
   Video. Belum ada endpoint `/api/v8/audio` terpisah — sengaja, karena ekstraksi audio adalah
   turunan dari post video.
3. **Kandidat format video/MP3 belum terintegrasi.** `clipora_v8_formats_lab` tidak diimpor
   aplikasi, tidak disajikan HTTP, dan tidak masuk image. MP3 yang tampil di UI masih berupa
   preferensi dan file sampel, bukan konversi FFmpeg nyata.
4. **Kode arsip Tools** (`tools_archive/device-preview`) disimpan sebagai referensi, tidak
   dimuat produk, dan diuji mengembalikan `404`.
5. **Mode demo mengirim file contoh.** `--demo-downloads` menyajikan empat file sampel di
   `assets/demo/` (±92 KB) plus caption contoh yang ikut dibundel. Preview, caption, dan file
   itu bukan isi post yang ditempel; tidak ada request keluar. File demo tidak masuk image
   produksi (allowlist `FILES` di `build_image.py`), dan route-nya tidak pernah didaftarkan pada
   origin HTTPS. Gate publik tetap `503`.
6. **Post gambar belum punya jalur ekstraksi.** Uji 12 URL (17 Okt 2026, IP rumah) menunjukkan
   8/8 URL video terbaca, tetapi 4/4 post gambar gagal: TikTok menolak `/photo/` (`Unsupported
   URL`), Instagram membalas `There is no video in this post`, Pinterest `No video formats
   found!`. yt-dlp hanya menangani video, jadi halaman Photo Downloader baru menyelesaikan
   bagian pengenalan dan tampilan — bukan pengambilan gambar. Pekerjaan ini masuk Fase 2
   (ROADMAP 4.2.1) dan harus selesai sebelum fitur gambar dijanjikan ke pengguna.

## Patch OS tertunda

Belum diterapkan; menunggu kandidat terpisah.

| Source | Terpasang | Target minimum |
| --- | --- | --- |
| expat | 2.8.3-1~deb13u1 | 2.9.0-1~deb13u1 |
| jpeg-xl | 0.11.2-0.1~deb13u2 | 0.11.2-0.1~deb13u3 |
| xz-utils | 5.8.1-1+deb13u1 | 5.8.1-1+deb13u2 |

Python juga membawa salinan `expat` sendiri (2.8.5) yang perlu ditinjau terpisah. Selain itu ada
156 record "open review required" dan 4 "undetermined" yang belum dinilai. Rincian:
[docs/OS_PACKAGE_REVIEW.md](docs/OS_PACKAGE_REVIEW.md).

## Jalan berikutnya

Urutan yang masuk akal: siapkan host staging Linux → tutup enam bloker di atas → audit ulang
image → baru pertimbangkan gate publik. Rencana lengkap per fase, estimasi waktu, biaya dan
kriteria keluar ada di [ROADMAP.md](../../ROADMAP.md). Rencana milestone historis ada di
[docs/MVP_READINESS.md](docs/MVP_READINESS.md).
