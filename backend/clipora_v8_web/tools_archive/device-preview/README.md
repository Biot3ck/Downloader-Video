# Kode tersimpan untuk calon Tools

Salinan kode preview file perangkat sebelum fitur dihapus atas permintaan pemilik. Tidak diimpor/dijalankan, tidak dilayani lewat HTTP, dan tidak masuk image web. Tidak mengaktifkan input file di produk atau egress publik.

images.js menyimpan validasi header/batas JPEG/PNG/WebP dan ZIP browser; previous-app.js/previous-ui.html/previous-style.css adalah referensi wiring lama. Adapter UI dan namespace elemen perlu disesuaikan sebelum penggunaan kembali pada Tools. Library murni dapat diperiksa dengan node tools_archive/device-preview/test_images.cjs; kode ini tetap di luar produk dan image web. Tidak ada file pribadi atau state sesi pada arsip ini.
