# Bukti isolasi Linux offline dan rencana penutupan blocker

## Hasil tahap ini

`run_linux_isolation.py` membuat dua jaringan internal dan tiga container disposable menggunakan image lokal. Tidak ada pull/build, bind mount, Docker socket, port publik, NET_ADMIN, mode privileged, perubahan firewall host, atau koneksi ke alamat publik. Container gateway pada tes ini adalah listener kontrol pada dua jaringan, bukan proxy HTTP Clipora. Tujuannya membuktikan topologi jaringan dan pembatasan kernel; jalur unduhan nyata tetap dibuktikan suite TLS/Compose terpisah.

Worker non-root hanya terhubung ke jaringan depan. Listener gateway dapat dicapai. Worker ditolak saat menghubungi listener egress di jaringan belakang dengan IP langsung, sementara kontrol positif dari container gateway berhasil menghubungi egress yang sama. IPv4 default route dan IPv6 default route yang usable tidak ada. Ini bukti keterpisahan dua namespace jaringan pada setup tes ini, bukan bukti kebijakan firewall untuk egress publik.

Dari dalam worker, seluruh capability set (inheritable/permitted/effective/bounding/ambient) bernilai nol, NoNewPrivs aktif, setuid root dan raw socket mendapat EPERM. Root write mendapat EROFS. Workspace tmpfs 1 MiB memiliki noexec/nosuid/nodev: eksekusi mendapat EACCES dan penulisan melewati kapasitas mendapat ENOSPC. Nilai 1 MiB sengaja memperkecil fixture pengujian; runner unduhan tetap memakai 64 MiB. Batas memory 128 MiB, CPU 1, dan PID 32 diperiksa lewat Docker inspect, belum diuji sampai kehabisan resource.

Resource diberi label unik. Cleanup memeriksa label sebelum menghapus nama yang dibuat tes. Tidak ada container/network tes tersisa, dan semua ID container yang sudah ada sebelum tes masih ada. Environment yang terdeteksi adalah Linux / Docker Desktop di macOS, bukan host Linux produksi.

## Audit publik tetap gagal tertutup

Audit lama dijalankan tanpa perubahan: 26/32, `PUBLIC_EGRESS_ENABLED=NO`. Lima gate memakai False eksplisit dan satu gate mendeteksi subnet test hard-coded. Skor ini bukan ukuran persentase keamanan dan tidak akan dinaikkan hanya karena tes offline lulus. File firewall test lama yang mengizinkan 1.1.1.1 tidak dijalankan pada tahap ini.

| Prioritas | Blocker yang tetap terbuka | Pekerjaan dan bukti penerimaan yang diperlukan |
| --- | --- | --- |
| P0 | Firewall produksi masih terkait subnet test 172.20.0.0/16 | Rancang konfigurasi topologi eksplisit; validasi alamat gateway terhadap jaringan yang dikonfigurasi; tolak missing/invalid/ambiguous config. Uji di namespace Linux disposable, termasuk startup gagal tanpa aturan lengkap. Jangan mengganti skrip stable/test lama langsung. |
| P0 | Allowlist publik belum dibatasi firewall independen | Rancang controller kebijakan dengan default DROP IPv4/IPv6, izin tujuan/port terbatas, deny private/metadata, tanpa jalur bypass DNS/UDP/QUIC. Buktikan penolakan koneksi langsung dan perubahan kebijakan dari proses aplikasi. Tahap offline hanya boleh memakai sink internal sintetis. |
| P0 | Binding IP tujuan belum dibuktikan di host Linux | Hubungkan hasil validasi DNS lengkap ke IP socket dan izin firewall yang sama; tidak melakukan resolve kedua saat dial. Uji rebinding, mixed A/AAAA, expiry, redirect, koneksi bersamaan, dan kegagalan update aturan. Fixture IP publik sintetis hanya boleh berada di namespace tanpa internet. |
| P0 | Drop capability sesudah konfigurasi firewall belum terbukti | Pisahkan bootstrap aturan dari proses layanan tanpa privilege. Uji CapEff/CapPrm/CapBnd/CapAmb dan NoNewPrivs sesudah startup, penolakan perubahan aturan dari layanan, serta fail-closed bila bootstrap gagal. Bukti worker tanpa capability saat ini belum membuktikan bootstrap egress. |
| P1 | TLS jalur unduhan produksi belum diuji | Gunakan konfigurasi calon produksi dan URL fixture; buktikan CA/hostname salah, downgrade, dan redirect lintas tujuan ditolak melalui worker → gateway → egress. Suite offline sekarang membuktikan harness, belum konfigurasi produksi. |
| P1 | Kuota disk keras dan sustained download belum diuji | Tentukan batas staging host yang ditegakkan filesystem, termasuk inode, log, DB/WAL, dan file sementara. Uji unduhan offline berulang/bersamaan, disk penuh, pembatalan, crash, dan retensi. tmpfs worker dan batas aplikasi staging belum sama dengan kuota disk host. |

## Urutan implementasi berikutnya

1. Susun harness firewall terpisah pada VM Linux disposable tanpa uplink, dengan dua lapisan isolasi dan cleanup terverifikasi. Belum ada VM Linux terpisah yang tersedia pada sesi ini. Docker Desktop dapat dipakai untuk prototipe namespace, tetapi hasilnya harus diberi scope yang tepat.
2. Tinjau rancangan bootstrap firewall, konfigurasi jaringan, dan binding IP sebelum mengubah implementasi egress. Ini perubahan keamanan signifikan yang perlu persetujuan pengguna.
3. Implementasikan di paket v8 baru dengan tes negatif dan fault injection. Pertahankan deny-all egress aktif dan v7 utuh.
4. Setelah bukti tiap gate lengkap, perbarui audit dengan pemeriksaan berbasis bukti yang dapat direproduksi; jangan mengganti False dengan True statis.
5. Aktivasi internet publik dan deployment tetap memerlukan persetujuan terpisah.

## Reproduksi lokal

Dari backend, gunakan `.venv/bin/python -B clipora_v8_verified_tls/run_linux_isolation.py /absolute/output/report.json`. Script memerlukan Docker aktif dan image `clipora-worker:v8-dns` sudah tersedia. Tidak akan mengambil image dari internet. Tes gagal bila invariant tidak terpenuhi; resource berlabel miliknya dibersihkan pada finally. SIGKILL terhadap harness itu sendiri belum diuji dan dapat memerlukan cleanup label manual.
