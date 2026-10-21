# Status Clipora v8

Diperbarui: 18 Oktober 2026. **Dokumen ini adalah satu-satunya sumber angka tes dan status
bloker.** Dokumen di [docs/](docs/) adalah catatan audit pada saat penulisannya; bila angkanya
berbeda, yang berlaku adalah angka di sini dan hasil eksekusi tes.

## Ringkasan

| Pertanyaan | Jawaban |
| --- | --- |
| Siap unduhan publik? | **Tidak.** Gate `503`, `ready_for_public_launch: false` |
| Siap demo internal? | **Ya**, dengan state privat dan hanya loopback |
| Fitur aktif | Pengenalan link Video, Photo & Audio; format Video, Video HD, MP3; **unduhan nyata opt-in** (`--real-downloads`, hanya loopback) |
| Fitur belum ada | Ekstraksi media di image publik; proxy media berskala produksi |
| Bloker publik terbuka | 6 (butuh host staging Linux terpisah) |
| Jalur rilis | Disiplin enam bloker; rilis bertahap/undangan ditolak (17 Okt 2026) |

## Tes

Dijalankan dari direktori `backend` dengan Python 3.15 pada image lokal:

| Paket | Jumlah | Perintah |
| --- | ---: | --- |
| `clipora_v8_web` | 124 | `.venv/bin/python -B -m unittest discover -s clipora_v8_web -p 'test*.py' -q` |
| `clipora_v8_formats_lab` | 8 | idem, ganti direktori |
| `clipora_v8_firewall_candidate` | 46 | idem |
| `clipora_v8_verified_tls` | 35 | idem |
| `clipora_v8_secure_egress_stage` | 25 | idem |
| `clipora_v8_staging_linux` | 8 | idem |
| `clipora_v8_image_backend` | 17 | idem |
| `clipora_v8_local_workflow` | 6 | idem |
| `clipora_v8_spike` | 33 | idem (fungsi murni; tanpa jaringan) |
| JavaScript frontend | 24 | `node clipora_v8_web/test_frontend_async.cjs` |
| **Total** | **326** | |

Tes ini membuktikan perilaku kode pada lingkungan lokal. Tes ini **bukan** pentest dan bukan
bukti kesiapan deployment. Angka 26/32 pada audit legacy adalah check yang sebagian memang
dihardcode belum terbukti, bukan skor.

## Unduhan nyata (opt-in)

`run_local.py --real-downloads` (atau `CLIPORA_REAL_DOWNLOADS=1`) mendaftarkan route
`/api/v8/real/*` hanya bila tiga syarat terpenuhi: flag aktif, permintaan datang dari loopback,
dan origin sama. `/api/v8/download` tetap `503`, dan `ready_for_public_launch` tetap `false`.
Mode ini sekarang ikut terpaket di image deployment `deploy/staging` (lock ber-hash, FFmpeg,
`real_media.py`, `yt-dlp`, `curl_cffi`), tetapi tetap **tidak** aktif pada origin publik: route
nyata hanya mendaftar untuk origin loopback. TikTok dari IP datacenter **membutuhkan**
`--impersonate` (`curl_cffi`); tanpa itu success rate-nya 0% (lihat bagian Fase 0.5 di bawah).

| Batas | Nilai |
| --- | --- |
| Ukuran per file | 100 MB |
| Ukuran per gambar | 10 MB |
| Total carousel | 50 MB, maksimum 20 gambar |
| Durasi video | 600 detik |
| Unduhan bersamaan | 2 |
| TTL token | 900 detik |
| Cache | 1 jam |

Verifikasi manual 18 Oktober 2026 (browser nyata, server loopback port 8090):

| Kasus | Hasil |
| --- | --- |
| TikTok video standar | 720×1280, 20,8 MB, H.264/AAC |
| TikTok video HD | 1080×1920, 37,6 MB, H.264/AAC |
| TikTok MP3 | MPEG layer III 192 kbps 44,1 kHz stereo |
| TikTok photo | 7 gambar, ZIP 849 KB, preview 816×1452 |
| Instagram reel | 360×640, 1,2 MB; durasi diisi dari `loadedmetadata` |
| Instagram carousel | 2 gambar, ZIP |
| YouTube video | 1280×720, 9,9 MB, 30 detik |
| YouTube MP3 | 192 kbps, 386,5 detik, 9,3 MB |
| Pinterest video | 360×640, 1,9 MB |
| Pinterest image | 361×543, JPEG |

Catatan kejujuran: Instagram tanpa login hanya memberi stream resolusi rendah; Pinterest kerap
hanya menyimpan satu ukuran asli. Angka di atas adalah hasil satu kali uji manual, bukan
success rate — itu tetap tugas Fase 0.5 di host yang sah.

## Image deployment (`deploy/staging`)

Image untuk host nyata dibangun dari `python:3.15-slim-trixie` (digest multi-arsitektur) +
FFmpeg, tanpa mewarisi image worker. Isinya: surface web, `real_media.py`, dua modul bersama
(`job_store`, `artifact_delivery`), `yt-dlp`, `httpx`, `curl_cffi`, dan lock runtime ber-hash
untuk linux/arm64 + amd64 (`deploy/staging/requirements-runtime.lock`).

Bukti 18 Oktober 2026, container lokal:

| Pemeriksaan | Hasil |
| --- | --- |
| 124 tes web di dalam image | lulus |
| `/healthz` | `public_downloads_enabled: false`, `ready_for_public_launch: false` |
| Preview TikTok | 720×1280, 49 detik, caption utuh |
| MP3 TikTok | `audio/mpeg`, 1,2 MB, 49,97 detik, 192 kbps |
| HD TikTok | MP4 1080×1920, 36 MB, H.264 |
| `POST /api/v8/download` | `503` |
| `/api/v8/real/*` pada origin HTTPS | `404` (tidak terdaftar) |

Compose menjalankan web di belakang Caddy dengan TLS, `read_only`, `cap_drop: ALL`,
`no-new-privileges`, dan batas memori/PID. Uji ekstraksi di host memakai overlay loopback
(`compose.real-test.yaml`) lewat SSH tunnel; instance publik tetap tanpa route nyata. Panduan:
`deploy/staging/README.md` dan `deploy/oracle/README.md`.

Review paket OS diulang 21 Oktober 2026 terhadap image `clipora-web:staging` (bukan image lama).
Delapan temuan `upgrade_required` hilang — expat 2.9.0, jpeg-xl u3, dan xz-utils u2 sudah
terpasang. Sisa 156 open + 8 undetermined adalah advisory yang belum diperbaiki di trixie dan
masih butuh triage reachability; belum ada sign-off keamanan. Rincian di
[docs/OS_PACKAGE_REVIEW.md](docs/OS_PACKAGE_REVIEW.md).

## Fase 0.5 — hasil jalur sah (GitHub Actions, 18 Oktober 2026)

Workflow `spike` dijalankan dari runner Azure (IP `4.149.237.36` dan `20.55.162.193`), 80 URL
yang sama (20 per platform), yt-dlp 2026.08.19. Ini **batas bawah**, bukan VPS khusus, tetapi
cukup untuk memisahkan masalah IP dari masalah toolchain.

| Platform | Mode default | `--impersonate chrome` |
| --- | ---: | ---: |
| TikTok | 0/14 (0%) | **14/14 (100%)** |
| Instagram | 13/13 (100%) | 13/13 (100%) |
| Pinterest | 2/2 (100%) | 2/2 (100%) |
| YouTube | 0/20 (0%) | 0/20 (0%) |

- **TikTok:** kegagalan default bukan reputasi IP, melainkan fingerprint TLS. Satu flag
  `--impersonate chrome` menaikkannya dari 0% ke 100%. `real_media.py` sekarang memakai target
  itu bila `curl_cffi` terpasang.
- **YouTube:** tiga client (`android_vr`, `tv`, `web_embedded`) diuji terpisah, semuanya 0/20
  dengan *Sign in to confirm you're not a bot*. Tanpa cookie/PO token tidak ada jalur sah dari
  IP datacenter. **YouTube ditangguhkan dari janji publik** (ROADMAP 4.4). Sejak 21 Oktober 2026
  YouTube tidak lagi muncul di teks bantuan atau daftar platform UI; `platforms.py` tetap
  menerima link YouTube untuk uji lokal.
- **Keputusan 4.3:** **LANJUT**. Ruang lingkup publik v1: TikTok, Instagram, Pinterest.
- Laporan mentah: `backend/clipora_v8_spike/RESULTS.md` (ringkasan tanpa URL). Berkas per URL
  tetap lokal di `hasil/` karena memuat tautan pihak ketiga.

Post gambar tidak masuk angka ini (spike menguji video); jalur gambar tetap seperti diuji manual
di atas.

## Bloker persetujuan publik

Belum ada yang bisa ditutup tanpa host staging Linux terpisah. Pada 18 Oktober 2026 pemilik
memilih **Oracle Cloud Always Free** sebagai host staging; VM belum dibuat, jadi status yang jujur
masih **demo internal**, bukan "hampir siap". Image kandidat dan panduan deployment sudah tersedia
di `deploy/staging` dan `deploy/oracle`; bukti enam bloker baru bisa dikumpulkan setelah host ada.

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

1. **Dua jalur build image.** Image deployment ada di `deploy/staging`: dibangun dari
   `python:3.15-slim-trixie` (digest multi-arsitektur) + FFmpeg + lock runtime ber-hash, tanpa
   mewarisi image worker. Jalur lama `build_image.py`/`Dockerfile`/`base_image.lock` masih
   mewarisi `clipora-worker:v8-dns`, tidak bisa dipakai di host baru, dan kini hanya untuk
   staging offline. Jangan memakai jalur lama untuk deployment.
2. **History dihapus dari surface; Audio sekarang nyata.** Menu History tidak ada di markup,
   JavaScript, maupun route demo (`/api/v8/history` → `404`). Halaman Audio Downloader sudah
   aktif: input URL video, preview pemutar audio, dan tombol **Download MP3**. Audio memakai
   kontrak pengenalan yang sama dengan video (`media_kind=video`), dengan `media_kind=audio`
   hanya pada endpoint preview demo. Format MP3 juga masih tersedia sebagai pilihan di halaman
   Video. Belum ada endpoint `/api/v8/audio` terpisah — sengaja, karena ekstraksi audio adalah
   turunan dari post video.
3. **Kandidat format video/MP3 belum terintegrasi.** `clipora_v8_formats_lab` tidak diimpor
   aplikasi, tidak disajikan HTTP, dan tidak masuk image. Di mode demo, MP3 masih file sampel.
   Di mode nyata (`--real-downloads`), MP3 adalah konversi FFmpeg sungguhan dari stream audio
   post, dan video dinormalkan ke H.264/AAC agar bisa diputar browser.
4. **Kode arsip Tools** (`tools_archive/device-preview`) disimpan sebagai referensi, tidak
   dimuat produk, dan diuji mengembalikan `404`.
5. **Mode demo mengirim file contoh.** `--demo-downloads` menyajikan empat file sampel di
   `assets/demo/` (±92 KB) plus caption contoh yang ikut dibundel. Preview, caption, dan file
   itu bukan isi post yang ditempel; tidak ada request keluar. File demo tidak masuk image
   produksi (allowlist `FILES` di `build_image.py`), dan route-nya tidak pernah didaftarkan pada
   origin HTTPS. Gate publik tetap `503`.
6. **Post gambar hanya tertangani di mode nyata.** Uji 12 URL (17 Okt 2026, IP rumah) dengan
   jalur yt-dlp lama menunjukkan 4/4 post gambar gagal. `real_media.py` sekarang punya pembaca
   per platform (TikTok `imagePost`, Instagram carousel, Pinterest `originals` + `og:image`)
   dan sudah diuji manual: TikTok 7 gambar, Instagram 2 gambar, Pinterest 1 gambar. Angka
   success rate lintas platform tetap harus diukur di jalur sah (ROADMAP 4.2.1/4.3); mode demo
   dan image publik belum punya jalur gambar.
7. **Mode nyata sudah terpaket, gerbang publik belum.** `deploy/staging` memuat `real_media.py`,
   `yt-dlp`, `httpx`, `curl_cffi`, dan FFmpeg dengan lock ber-hash; 124 tes web lulus di dalam
   image, dan ekstraksi TikTok/MP3/HD sudah diverifikasi di container. Yang tersisa bukan
   pemaketan, melainkan (a) gerbang publik dan enam bloker, (b) jalur `build_image.py` lama yang
   tidak dipakai lagi untuk deployment, dan (c) keputusan produk soal YouTube. Kualitas sumber
   tetap dibatasi platform: Instagram tanpa login memberi stream resolusi rendah (360×640 pada
   uji), Pinterest kadang hanya menyimpan satu ukuran asli. UI menampilkan ukuran sebenarnya,
   bukan angka yang dijanjikan.

## Bukti uji manual mode nyata (18 Okt 2026)

Server `--real-downloads` di port 8090, browser Chromium, IP rumah `88.230.177.250`. Ini uji
fungsional satu kali, **bukan** success rate; angka success rate tetap milik Fase 0.5.

| Post | Format | Hasil |
| --- | --- | --- |
| TikTok `@tiktok/video/7694797676306615583` | Video | 720×1280, 49,9 s, 20,8 MB, H.264/AAC |
| idem | Video HD | 1080×1920, 49,9 s, 37,6 MB, H.264/AAC |
| idem | MP3 | 192 kbps, 44,1 kHz, stereo, 1,2 MB |
| TikTok `@catphotovideo0/photo/7690397576977206536` | Gambar | 7 gambar, ZIP 849 KB, preview 816×1452 |
| Instagram `reel/DeewiSPpCrm` | Video | 360×640, 10,9 s, 1,2 MB |
| Instagram `p/DanZcCTDrdx` | Gambar | 2 gambar, ZIP |
| YouTube `watch?v=n_G4dQMKYN0` | Video | 1280×720, 30,1 s, 9,9 MB |
| YouTube `watch?v=wGA27zJEnaU` | MP3 | 192 kbps, 386,5 s, 9,3 MB |
| Pinterest `pin/2392606047526589` | Video | 360×640, 34,9 s, 1,9 MB |
| Pinterest `pin/146367056616629683` | Gambar | JPEG 361×543, 37 KB |

Catatan: post gambar yang ditempel di halaman Video sekarang ditolak dengan pesan
"This post contains photos only. Use the Photo Downloader.", dan opsi unduhan disembunyikan.
Durasi yang tidak dilaporkan platform (mis. Instagram) diisi dari `loadedmetadata` pemutar.

## Review paket OS image deployment (21 Oktober 2026)

Target: `clipora-web:staging`, ID `sha256:ae33b3545738fb422eadf376f7317252c089705d101eb51c74aeefeab3ced286`,
Debian 13/trixie aarch64, Python 3.15.0. Snapshot tracker 84.480.930 byte, SHA256
`c854eb210775bcc75ce78f8ac04a45715ed94d0dc81f7d430113e1d2b4a8d28e`.

| Kategori | Image baru | Image lama 17 Okt |
| --- | ---: | ---: |
| Fixed pada versi terpasang | 2.613 | 2.605 |
| Upgrade required | **0** | 8 |
| Open review required | 156 | 156 |
| Undetermined | 8 | 8 |
| Debian unimportant | 320 | 320 |
| Marker not affected | 325 | 325 |

Tiga patch yang tertunda sudah terpenuhi di image baru: expat `2.9.0-1~deb13u1`, jpeg-xl
`0.11.2-0.1~deb13u3`, xz-utils `5.8.1-1+deb13u2`. Sisa open/undetermined belum diperbaiki di
trixie; yang paling relevan adalah `ffmpeg`/`libav*` (37 record) karena memproses media pengguna.

Mitigasi: `ffmpeg`/`ffprobe` sekarang dijalankan dengan `-protocol_whitelist file`, `-nostdin`,
demuxer yang dipatok dari allowlist, dan allowlist codec input. File yang diunduh tidak bisa
memicu bukaan URL jaringan, memilih parser kontainer lain, atau menjangkau decoder di luar
h264/hevc/vp8/vp9/av1/aac/opus/mp3. TikTok nyata (h264/aac) dan WebM vp9/opus lulus.

`pip-audit 2.10.1` atas 21 paket runtime menemukan satu advisory: `certifi 2026.7.22`
(`PYSEC-2026-4320`). Lock dan `requirements-dev.txt` sudah naik ke `certifi 2026.10.19`, audit
ulang bersih, dan image dibangun ulang. Review ini belum menjadi persetujuan: kernel/host,
library bundled Python, dan pemantauan advisory berkala belum tercakup.

## Jalan berikutnya

Urutan yang masuk akal: Fase 0.5 sudah memberi lampu hijau dari IP Azure (TikTok 100% dengan
impersonation, YouTube ditangguhkan) → siapkan host staging Linux → tutup enam bloker di atas →
audit ulang image → baru pertimbangkan gate publik. Rencana lengkap per fase, estimasi waktu,
biaya dan kriteria keluar ada di [ROADMAP.md](../../ROADMAP.md). Rencana milestone historis ada
di [docs/MVP_READINESS.md](docs/MVP_READINESS.md).
