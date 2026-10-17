# Review paket OS dan persiapan Linux staging — 17 Oktober 2026

Review pencocokan versi OS sudah dijalankan. **Hasil: perlu patch dan triage lanjutan; belum disetujui untuk publik.** Pemilik kembali memilih tanpa VM. Tidak memasang paket/VM, mengubah Docker context, memodifikasi container/image aktif, menyentuh VPS atau membuka egress downloader.

## Target dan metode

Target persis: image lokal `sha256:4ca92458f098893504d317d7f1c2301ccbaa81fc1cb4fce5edb0a1f0a5dc3944`, Debian 13/trixie, aarch64. Ada 289 binary package terpasang dari 207 pasangan source/version. Image web saat ini mewarisi image worker sehingga ikut membawa FFmpeg dan banyak library codec; pengurangan image web menjadi runtime API minimal perlu dilakukan pada kandidat terpisah.

Data binary/source/version/status dibaca dengan dpkg-query dalam container disposable readonly, network none, non-root, cap-drop ALL/no-new-privileges, CPU/memori/PID terbatas. Source version dibandingkan memakai dpkg --compare-versions, bukan pembandingan string atau versi upstream saja. Ini mempertimbangkan epoch, revisi Debian dan backport. [Dokumentasi dpkg-query](https://manpages.debian.org/trixie/dpkg/dpkg-query.1.en.html), [penjelasan backport Debian](https://www.debian.org/security/faq#oldversion).

Snapshot [Debian Security Tracker](https://security-tracker.debian.org/tracker/data/json) diambil melalui HTTPS oleh alat audit host, 83.193.478 byte, SHA256 `9afcba95f725531a267de8d894a8aabb67b435358f2eb2bfa3fade2e5af17bce`. Snapshot/hash membekukan data untuk reproduksi; bukan tanda tangan persetujuan Debian atau Clipora. Tidak mengirim nama project, URL video, cookie, environment atau secret ke layanan tersebut.

## Hasil pencocokan

| Kategori source/advisory | Jumlah | Makna |
| --- | ---: | --- |
| Fixed pada versi terpasang | 2.605 | Versi sumber memenuhi fixed_version tracker |
| Marker not affected | 325 | Tracker memberi fixed_version=0 |
| Debian unimportant | 320 | Disimpan eksplisit; tidak dihitung sebagai temuan runtime yang sudah terbukti, bukan risk acceptance otomatis |
| Upgrade required | 8 | Tujuh CVE dan satu identitas sementara pada tiga source package; patch tersedia |
| Open review required | 156 | Masih memerlukan penilaian jalur kode/fitur/konfigurasi yang dapat dicapai |
| Undetermined | 4 | Status belum pasti; tidak boleh dianggap bersih |

Sebanyak 74 nama source tidak mempunyai record pada snapshot tracker; itu cakupan yang tidak mempunyai data, bukan bukti bebas kerentanan. Daftar rinci dan paket binary terkait ada di outputs/clipora-os-package-review-final.json pada workspace chat. Angka adalah pasangan source/advisory, bukan jumlah paket, severity, ataupun bukti bahwa seluruh isu dapat dieksploitasi pada Clipora. No-dsa tidak diartikan sebagai aman. [Arti klasifikasi Debian](https://security-team.debian.org/security_tracker.html#severity-levels).

## Prioritas patch kandidat terpisah

| Source → binary terpasang | Versi sumber saat ini | Target minimum trixie yang ditemukan |
| --- | --- | --- |
| expat → libexpat1:arm64 | 2.8.3-1~deb13u1 | 2.9.0-1~deb13u1 |
| jpeg-xl → libjxl0.11:arm64 | 0.11.2-0.1~deb13u2 | 0.11.2-0.1~deb13u3 |
| xz-utils → liblzma5:arm64 | 5.8.1-1+deb13u1 | 5.8.1-1+deb13u2 |

Referensi: [Expat/DSA-6566-1](https://security-tracker.debian.org/tracker/CVE-2026-102633), [JPEG XL/DSA-6564-1](https://security-tracker.debian.org/tracker/CVE-2026-52584), [advisori upstream XZ GHSA-5qpq-xqfv-j9pg](https://github.com/tukaani-project/xz/security/advisories/GHSA-5qpq-xqfv-j9pg). Daftar lengkap enam CVE Expat, satu CVE JPEG XL dan record sementara XZ tersimpan di report. Kesesuaian versi paket bukan penilaian exploitability: beberapa isu mempunyai syarat arsitektur/fitur tertentu yang harus ditinjau.

Pemeriksaan linkage aktual menunjukkan FFmpeg menautkan libexpat/libjxl/liblzma, sedangkan modul lzma Python menautkan liblzma. pyexpat Python melaporkan expat_2.8.5 dan tidak menautkan libexpat sistem pada hasil ldd; perlakukan sebagai Expat bundled yang memerlukan review/rebuild Python tersendiri. Meng-upgrade libexpat1 saja tidak membuktikan library bundled itu ikut diperbarui. Hasil lain: Python 3.13.16, OpenSSL 3.5.7, sqlite 3.46.1, FFmpeg 7.1.5-0+deb13u1. Bukti: outputs/clipora-os-native-linkage.json. Review ini tidak mencakup semua library bundled/native, host/kernel Linux atau dependency Python.

Empat undetermined berasal dari game-music-emu, PAM dan zvbi. Temuan open antara lain berada pada FFmpeg serta library XML, font, gambar/audio dan sistem. Tetap tercatat untuk triage; isolation/resource limit tidak otomatis menutup kerentanan parser.

## Kode audit yang disiapkan

os_review.py tidak dimuat FastAPI/worker dan tidak masuk image build. Tool hanya membaca image lokal dan snapshot yang disediakan. Tidak mengunduh/menginstal apa pun. Hanya source audit ini disalin ke temporary readonly mount; snapshot disaring di host, lalu versi dibandingkan di container network none. Nama/versi tervalidasi diteruskan lewat argv tanpa shell. Cleanup hanya container dengan nama/label unik milik tool.

Dari backend, memakai snapshot dan image yang sudah ditinjau:

```sh
.venv/bin/python -B clipora_v8_web/os_review.py \
  --image-id sha256:4ca92458f098893504d317d7f1c2301ccbaa81fc1cb4fce5edb0a1f0a5dc3944 \
  --tracker /absolute/cache/debian-tracker.json \
  --tracker-sha256 9afcba95f725531a267de8d894a8aabb67b435358f2eb2bfa3fade2e5af17bce \
  --report /absolute/new/os-review.json
```

Report baru dibuat 0600 dan file yang ada tidak ditimpa. Exit 2 sengaja menandakan review tidak memberikan persetujuan produksi; periksa report untuk membedakannya dari kegagalan command. Snapshot baru harus diambil ulang dari sumber resmi dan hash/waktu pengambilan dicatat, bukan memakai hash lama terhadap data baru. Enam tes kontrak mencakup pemakaian source version, fixed/not-affected, no-dsa/unimportant, status/data hilang dan input malformed. Perbandingan versi Debian aktual juga dijalankan pada image yang diperiksa.

Regresi tahap ini: 83 tes Python web (termasuk enam tes audit OS), delapan tes preflight staging dan tujuh tes JavaScript lulus, total 98. Source audit baru tidak ada dalam allowlist image web. Tidak perlu restart preview atau rebuild image karena aplikasi aktif tidak diubah.

## Urutan staging/patch berikutnya

1. Tetapkan snapshot advisori, image ID, binary/source package dan target patch yang ditinjau. Buat kandidat image dengan tag/digest baru; base/worker stabil dan container aktif tidak ditimpa.
2. Ambil paket hanya dari repositori resmi Debian. Verifikasi tanda tangan InRelease dengan archive keyring yang dipercaya, lalu hash indeks/paket; hash unduhan yang dihitung sendiri tidak cukup sebagai bukti autentisitas paket. Review dependency closure dan arsitektur. Jangan menjalankan apt terhadap runtime aktif.
3. Bangun kandidat patch secara offline dari paket tervalidasi; perbarui provenance/SBOM. Tangani Expat bundled Python secara terpisah. Kandidat web minimal tidak perlu membawa FFmpeg/yt-dlp; worker tetap terisolasi.
4. Jalankan ulang audit OS/native/Python, smoke media MP4/gambar/HD/MP3, ownership/Range/TTL/cancel/recovery, dan suite tiga tier/mTLS. Temuan open/undetermined harus diberi keputusan beserta bukti, tanpa menghapus record agar hasil tampak bersih.
5. Setelah Linux staging terpisah disediakan pemilik, jalankan ../clipora_v8_staging_linux/preflight.py dan urutan README-nya. Transfer hanya bundle eksplisit + image terpin, tanpa .env/credential/seluruh Desktop. Uji quota byte/inode total, ENOSPC/sustained load, firewall/DNS/IP/TLS/controller/ingress pada kandidat yang sama.
6. Review hasil final dan rollback sebelum persetujuan keamanan/aktivasi terpisah. Sampai itu selesai, public gate tetap false/503. Docker Desktop tidak dinyatakan menggantikan host staging Linux terpisah.

Tahap ini menyelesaikan inventaris dan review pencocokan paket serta menyiapkan alat/rencana patch, **belum menerapkan patch atau menyelesaikan seluruh triage kerentanan**.
