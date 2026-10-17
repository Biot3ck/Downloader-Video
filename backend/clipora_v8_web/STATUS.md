# Status Clipora v8

Diperbarui: 17 Oktober 2026. **Dokumen ini adalah satu-satunya sumber angka tes dan status
bloker.** Dokumen di [docs/](docs/) adalah catatan audit pada saat penulisannya; bila angkanya
berbeda, yang berlaku adalah angka di sini dan hasil eksekusi tes.

## Ringkasan

| Pertanyaan | Jawaban |
| --- | --- |
| Siap unduhan publik? | **Tidak.** Gate `503`, `ready_for_public_launch: false` |
| Siap demo internal? | **Ya**, dengan state privat dan hanya loopback |
| Fitur aktif | Pengenalan link Video & Photo |
| Fitur belum ada | Audio, History, ekstraksi/konversi media |
| Bloker publik terbuka | 6 (butuh host staging Linux terpisah) |

## Tes

Dijalankan dari direktori `backend` dengan Python 3.15 pada image lokal:

| Paket | Jumlah | Perintah |
| --- | ---: | --- |
| `clipora_v8_web` | 81 | `.venv/bin/python -B -m unittest discover -s clipora_v8_web -p 'test*.py' -q` |
| `clipora_v8_formats_lab` | 8 | idem, ganti direktori |
| `clipora_v8_firewall_candidate` | 46 | idem |
| `clipora_v8_verified_tls` | 35 | idem |
| `clipora_v8_secure_egress_stage` | 25 | idem |
| `clipora_v8_staging_linux` | 8 | idem |
| `clipora_v8_image_backend` | 17 | idem |
| `clipora_v8_local_workflow` | 6 | idem |
| JavaScript frontend | 7 | `node clipora_v8_web/test_frontend_async.cjs` |
| **Total** | **233** | |

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
2. **Audio dan History belum ada.** Ditandai `Soon` di navigasi dan "Not available yet" di
   halamannya. Tidak ada API yang berpura-pura mendukungnya.
3. **Kandidat format video/MP3 belum terintegrasi.** `clipora_v8_formats_lab` tidak diimpor
   aplikasi, tidak disajikan HTTP, dan tidak masuk image.
4. **Kode arsip Tools** (`tools_archive/device-preview`) disimpan sebagai referensi, tidak
   dimuat produk, dan diuji mengembalikan `404`.

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
image → baru pertimbangkan gate publik. Rencana milestone historis ada di
[docs/MVP_READINESS.md](docs/MVP_READINESS.md).
