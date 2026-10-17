Status: pemasangan VM tidak disetujui; pemilik memilih persiapan kode saja pada 17 Oktober 2026. Jangan menjalankan instalasi berdasarkan dokumen ini.

# Usulan staging Linux lokal untuk persetujuan

Belum dijalankan. Dibuat 17 Oktober 2026. Mac ini ARM64, RAM 24 GiB, ruang disk bebas sekitar 589 GiB saat diperiksa. Docker Desktop tersedia; Lima, Multipass, QEMU dan Colima tidak ditemukan.

## Perubahan yang diminta

1. Memasang Lima beserta dependency yang diwajibkan Homebrew melalui `brew install lima`. Tidak mengubah Docker context aktif, konfigurasi SSH global, atau daemon Docker Desktop yang sedang digunakan Clipora.
2. Membuat satu VM bernama `clipora-staging`, Ubuntu 24.04 LTS ARM64, driver Apple VZ, 2 CPU, RAM 4 GiB, disk virtual maksimum 30 GiB. Home directory host tidak dimount; gunakan --plain dan --mount-none. Template/config divalidasi terhadap versi Lima yang benar-benar terpasang sebelum start. Tidak membuka port aplikasi ke LAN/internet.
3. Mengunduh image OS dari sumber resmi dan paket staging. Akses internet ini khusus penyediaan OS/dependency, bukan izin egress aplikasi downloader. Catat image/checksum dan versi paket. Jangan mengaktifkan downloader publik pada tahap provision.
4. Menyalin bundle runtime Clipora yang eksplisit ke disk VM tanpa .env, secret, arsip Desktop, atau source tree v7. Menjalankan Docker Engine dalam VM tanpa mengubah context host. Transfer image lokal melalui arsip bila memungkinkan agar tidak membangun dependency baru dari internet.
5. Menjalankan suite tiga tier dan tes host Linux di VM: firewall, routing, crash/restart, filesystem quota untuk semua state/artifact/temporary/WAL/log, sustained load terbatas, ingress loopback-only, serta catatan rollback. Kondisi gagal tidak mengubah gate menjadi ready.

VM dan proses memakai RAM/CPU saat berjalan; disk VM dan cache download tetap memakai penyimpanan sesudah stop. Lima membuat state/credential VM sendiri di direktori Lima; credential tidak dipublikasikan atau dicetak. Tidak ada akses VPS, deployment publik, atau aktivasi platform publik dalam persetujuan ini.

Rollback: stop/delete hanya VM clipora-staging setelah hasil yang diperlukan diekspor. Uninstall Lima tidak otomatis dilakukan karena dapat dipakai pekerjaan lain. Jangan menghapus VM lain, Docker Desktop, atau container Clipora yang sudah ada.

## Sumber resmi

- https://lima-vm.io/docs/installation/
- https://lima-vm.io/docs/reference/limactl_start/
- https://lima-vm.io/docs/templates/
- https://lima-vm.io/docs/config/vmtype/vz/

Konfigurasi ini merupakan rencana untuk dinilai; pemasangan VM membutuhkan persetujuan karena instruksi awal pemilik meminta persetujuan sebelum perubahan signifikan. Belum ada software baru yang dipasang oleh tahap ini.
