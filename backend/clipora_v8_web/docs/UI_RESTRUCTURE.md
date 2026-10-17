> Catatan: dokumen ini menyimpan rincian audit pada saat penulisannya. Status, angka tes, dan blocker terkini ada di [STATUS.md](../STATUS.md).
>
> **Perubahan 17 Oktober 2026:** surface dipersempit ke dua fitur. Menu Audio Downloader,
> menu History, dan format MP3 dihapus — bukan sekadar dinonaktifkan. Rincian di bawah yang
> menyebut empat menu atau MP3 adalah catatan historis.

# Clipora — restrukturisasi UI/UX

## Audit dan checkpoint

Frontend preview aktif berada pada paket ini: index.html, assets/app.js dan assets/style.css. FastAPI main.py menyediakan UI, config, pengenalan URL dan gate download 503. Launcher --offline-workflow menambahkan queue/ownership/worker sampel lokal yang sudah ada; tidak mengaktifkan internet. Desain rujukan `design/product_v8.html` (arsip read-only, tidak disajikan HTTP dan tidak masuk image) mempunyai identitas ungu #6255ea, latar #f8f9fd, wordmark clipora. dan font Inter/system. Identitas tersebut dipertahankan.

Proyek sebelumnya tidak mempunyai repositori Git. Checkpoint lokal d6593fc dibuat sebelum perubahan, hanya pada folder clipora_v8_web, dengan branch checkpoint/pre-ui-restructure. Implementasi memakai branch feat/frontend-navigation. Repo ini sengaja tidak mencakup v7, runtime state, cookie/database, .env atau seluruh Desktop. Tidak ada push/PR/deployment.

## Hasil implementasi

- Navigasi hash #video, #photo, #audio, #history tanpa framework baru, CDN, font download, analytics, atau API yang dibuat-buat. Satu form digunakan untuk video/foto; URL draft hanya di memori tab, tidak disimpan permanen.
- Video/Photo memanggil POST /api/v8/validate dengan kontrak media_kind yang sudah ada. Hasil hanya pengenalan platform. Tidak menampilkan thumbnail/judul/durasi/format/progres palsu; backend publik belum menyediakan metadata/download yang dapat dipakai. Pergantian menu membatalkan pemeriksaan lama dan mencegah hasil terlambat masuk ke menu baru.
- Audio memiliki interface khusus tetapi input/tombol dinonaktifkan. Tidak menawarkan MP3/kualitas atau memanggil endpoint audio yang belum ada.
- History menampilkan status belum tersedia. Belum ada API daftar job per pemilik pada surface produk; tidak menampilkan fixture sebagai riwayat unduhan nyata, tidak mengklaim penyimpanan permanen, tidak mengumpulkan data baru. API status/file individual dan retensinya tetap dipertahankan.
- Seluruh sampel dipindahkan dari index.html ke dev.html dengan assets/dev.js dan assets/dev.css. URL /dev dan asset tersebut hanya disajikan ketika flag offline eksplisit aktif pada origin HTTP loopback; default/HTTPS/container product tetap 404. Tidak ada link developer pada navigasi produk. API sampel lama tetap sama.
- Kode pemrosesan file perangkat dipulihkan dari backup lokal ke tools_archive/device-preview untuk calon Tools. Kode/tes referensi disimpan, tidak dimuat produk, tidak dilayani HTTP dan tidak masuk image Docker. Tidak ada pemilih file atau object/blob media pada produk.
- Satu panel utama, ruang yang lebih lega, navigasi desktop/mobile, kontras teks yang lebih jelas, fokus keyboard, skip link, label/aria-live, form busy/disabled, dan preferensi reduced-motion. Tidak mengubah TLS, DNS, SSRF, limiter, ownership, worker atau isolation.

## File yang berubah

| File | Perubahan |
| --- | --- |
| index.html | Empat fitur, form produk, unavailable state Audio/History, tanpa demo |
| assets/app.js | Navigasi/validasi link yang ada, abort/stale-response guard, fokus keyboard |
| assets/style.css | Layout/spacing/warna asli, breakpoint dan state interaksi |
| main.py | Route halaman/asset developer bersyarat offline + loopback; API publik tetap sama |
| dev.html, assets/dev.js, assets/dev.css | UI/utilitas sampel lama yang tetap dapat dipakai developer |
| tools_archive/device-preview/* | Referensi pemrosesan file/ZIP untuk Tools; tidak disajikan |
| test_frontend_navigation.py | Pemisahan produk/developer, empat menu, unsupported feature dan gate |
| test_images.py | Ekspektasi UI foto tanpa sampel pada halaman produk |
| README.md, IMAGES.md, MVP_READINESS.md | Dokumentasi surface baru dan keterbatasan |

build_image.py tetap memakai daftar file eksplisit, sehingga dev.html/assets dev/arsip Tools tidak masuk image web.

## Validasi

63 tes web + 17 backend gambar + 6 workflow lokal lulus (86 total). Node syntax check pada JS produk/developer dan tes library arsip Tools lulus. Runtime image web default/owned diuji internal, readonly/non-root/cap-drop; public download tetap 503 dan /dev tetap 404 pada kedua entrypoint container.

Browser aktual menguji menu Video/Photo/Audio/History pada viewport 1280×900, 768×900, 390×900 dan 320×900: 16 kombinasi, tidak ada overflow horizontal, tepat satu view aktif, navigasi minimal 44 px. Viewport override di-reset setelah pengujian. Ini pengujian layout browser, bukan sertifikasi perangkat fisik Android/iOS/Safari. Link video/foto dikenali melalui API aktual tanpa metadata palsu; Audio disabled dan History unavailable diverifikasi. Sampel album pada halaman developer tetap diproses oleh worker offline aktual.

Bukti dan screenshot disimpan pada folder outputs chat. Baseline sumber lama tetap hanya mempunyai lima perbedaan yang sudah diketahui sebelum tugas ini; ../main.py (v7) tetap byte-identical dengan main-v7-stable.py.

## Cara menjalankan

Dari backend, memakai runtime yang sudah ada:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --offline-workflow --port 8090 --state /absolute/private/state
```

Produk: http://127.0.0.1:8090/ (atau /app). Developer offline: http://127.0.0.1:8090/dev. Tanpa --offline-workflow halaman developer tidak tersedia. Jangan memakai launcher loopback sebagai deployment publik.

## Yang masih diperlukan

Extractor/download platform publik, metadata dan daftar format belum tersedia pada surface produk. API audio dan API list history berbasis pemilik/expiry belum diimplementasikan. Hubungkan fitur-fitur tersebut hanya setelah backend yang sesuai dan gate keamanan diterima; jangan mengganti gate dengan flag UI. Unduhan publik tetap dinonaktifkan, audit legacy tetap enam blocker. Tidak memasang VM, menyentuh VPS, atau deploy.

Rollback UI: hentikan preview setelah job selesai, gunakan checkpoint/pre-ui-restructure di repo frontend, lalu jalankan kembali launcher yang sama. Tidak ada migrasi data atau perubahan format job.

## Pemeriksaan lanjutan validasi tautan

Hasil pemeriksaan kini langsung dibersihkan ketika URL diedit. Request yang masih berjalan dibatalkan; respons lama tidak dapat menimpa request baru atau menu lain. Error layanan 5xx dan batas 429 ditangani sebelum parsing JSON, sehingga halaman error HTML/proxy tidak ditampilkan sebagai pesan teknis. Pesan validasi 422 dari API tetap dipertahankan; respons JSON rusak atau kontrak sukses yang tidak sesuai menghasilkan pesan kegagalan.

Perubahan lanjutan hanya assets/app.js, test_frontend_async.cjs dan dokumentasi ini. Enam unit test Node menguji pergantian input/menu, respons terlambat, 429/503, JSON rusak dan pesan validasi. Seluruh 86 tes Python tetap lulus (92 total), serta pemeriksaan container default/owned yang dijalankan berurutan setelah rebuild image offline. Browser aktual memverifikasi pengenalan video/foto, pembersihan hasil saat edit, penolakan URL platform lain dan viewport 390×844 tanpa overflow horizontal; viewport di-reset sesudahnya.

History tetap unavailable: brief mengharuskan penggunaan API yang sudah ada, sedangkan API daftar job milik sesi belum tersedia. Tidak membuat endpoint history, data riwayat permanen atau hasil fixture pada produk. Penyempurnaan ini tidak mengubah backend, v7, gate unduhan publik maupun kebijakan jaringan.
