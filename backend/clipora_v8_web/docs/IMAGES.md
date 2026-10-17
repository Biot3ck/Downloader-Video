> Catatan: dokumen ini menyimpan rincian audit pada saat penulisannya. Status, angka tes, dan blocker terkini ada di [STATUS.md](../STATUS.md).

# Mode gambar dan album Clipora

Mode Images / album mengenali link HTTPS TikTok, Instagram, dan Pinterest tanpa menghubungi platform. Request tanpa media_kind tetap mode video; URL publik tidak dimasukkan ke scheduler lokal. Pengambilan konten platform/extractor publik tetap belum tersedia, dan endpoint download tetap 503.

Launcher --offline-workflow menyediakan sampel album backend dengan worker Docker network none, pemeriksaan PNG/JPEG/WebP, manifest berurutan, publikasi atomik, ownership, cancel, retensi, unduh per gambar dan ZIP. Detail: ../clipora_v8_image_backend/README.md.

Atas permintaan pemilik, fitur On your device / No upload sudah dihapus: tidak ada pemilih file, preview file perangkat, object URL/blob media, atau ZIP yang dibuat browser. assets/images.js dan tes khusus library tersebut dihapus; asset/route/build tidak menyertakannya. Galeri hasil backend serta pilihan Video/Images tetap tersedia. CSP img-src/media-src hanya origin sendiri.

## Surface produk setelah restrukturisasi

Photo Downloader pada #photo hanya menampilkan pemeriksaan link publik yang sudah ada. Sampel/galeri hasil fixture dipindahkan ke /dev pada launcher offline loopback. Arsip pemrosesan file perangkat tetap disimpan di tools_archive/device-preview untuk calon Tools; kode tersebut tidak disajikan atau dimuat produk. Detail UI_RESTRUCTURE.md.
