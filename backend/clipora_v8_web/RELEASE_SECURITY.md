# Review keamanan publik — 17 Oktober 2026

**Keputusan: BELUM DISETUJUI untuk unduhan publik atau deployment.** Public gate tetap false/503. Pemilik mengonfirmasi belum ada Linux staging terpisah dan memilih pemeriksaan lokal; tidak ada VM/software baru, VPS atau konfigurasi host yang dipasang/diubah.

## Perbaikan lokal yang selesai

Limiter sebelumnya hanya menolak symlink pada direktori paling akhir/database. Ancestor symlink dan database yang sudah ada dengan izin terlalu terbuka belum ditolak. Sekarang path state harus kanonis tanpa ancestor symlink; direktori harus milik UID proses dengan mode 0700. Database harus regular, milik UID yang sama, mode 0600 dan tanpa hardlink tambahan. FIFO/perangkat/link ditolak menggunakan pemeriksaan tipe dan open nonblocking/nofollow. Validasi diulang pada setiap koneksi SQLite, termasuk setelah inisialisasi. Tidak mengubah chmod/isi file yang ditolak. Kesalahan admission HTTP menghasilkan 503 generik tanpa path privat.

Factory ownership membuat/memeriksa root state privat sebelum direktori artifact dan queue. Ini mencegah mkdir(parents=True) membuat root state baru dengan mode 0755. Aplikasi utama tetap mempunyai satu limiter middleware; factory ownership menginisialisasi instance yang sama saat startup. Tidak mengubah token, retensi, format database, v7, TLS, DNS, SSRF, firewall atau file media lama.

Ini perlindungan konfigurasi penyimpanan lokal; bukan isolasi terhadap administrator/root/Docker operator atau proses lain dengan UID yang sama yang menguasai filesystem. Pemeriksaan pathname bukan klaim eliminasi seluruh race filesystem. Root state harus ditempatkan pada lokasi tepercaya dan kuotanya diterapkan di host staging.

## Bukti terbaru

| Pemeriksaan | Hasil dan batas bukti |
| --- | --- |
| Unit/integrasi otomatis | 77 web + 46 firewall candidate + 35 verified TLS + 25 secure egress + 8 preflight + 17 gambar + 6 workflow + 7 JavaScript = 221 lulus |
| Image web default dan ownership | Rebuild offline; HTTP pada container internal, readonly, non-root, cap-drop; public download 503, developer routes 404 |
| Tiga tier/mTLS, worker yt-dlp aktual | Kasus valid menghasilkan MP4; wrong hostname dan CA tak dipercaya ditolak; bypass worker/gateway/peer diuji pada lease aktif; IPv6 DROP dan pencabutan lease terbukti pada namespace Docker |
| Crash/recovery aktual | SIGKILL hanya proses web disposable; helper tetap memegang leader lock; job terputus gagal, file parsial tidak disajikan; resource milik tes dibersihkan |
| Alur offline sesudah perbaikan | State baru privat → sesi → queue → worker Docker aktual → MP4 → owned file/Range/HEAD; sesi asing ditolak; gate HD/reward klien tetap 503 |
| Dependensi image | Lookup OSV untuk 17 pasangan nama/versi Python tanpa advisory yang cocok. Review Debian 289 binary/207 source-version menemukan delapan record yang memerlukan upgrade pada Expat, JPEG XL dan XZ, 156 open dan empat undetermined untuk triage; Expat bundled Python juga perlu review. Patch belum diterapkan. Lihat OS_PACKAGE_REVIEW.md |
| Preflight host | BLOCKED sebagaimana mestinya pada macOS; query daemon sengaja tidak dijalankan untuk attestation host Linux. Check yang dilewati berarti belum terbukti, bukan penemuan bahwa Docker tidak memiliki fitur tersebut |

Nama report pada outputs chat: clipora-security-current-kernel-valid.json, -kernel-wrong-host.json, -kernel-untrusted-ca.json, -web-default.json, -web-owned.json, -restart.json, -offline-flow.json, -inventory.json, -python-advisories.json dan -preflight.json. Inventory/advisory report menyertakan image ID yang diperiksa. Lookup Python menggunakan API resmi https://google.github.io/osv.dev/post-v1-querybatch/ melalui alat audit host; tidak membuka egress downloader/container atau mengirim URL pengguna/cookie/secret.

## Blocker untuk persetujuan publik

Audit legacy tetap 26/32 dengan enam blocker. Sebagian check legacy memang hardcoded sebagai belum terbukti; angka ini bukan skor pentest dan tidak diubah untuk menyatakan lulus. Bukti fixture baru belum memenuhi bukti deployment berikut:

| Blocker | Syarat penutupan |
| --- | --- |
| Firewall konfigurasi produksi | Topologi/route IPv4/IPv6 pada kandidat deployment yang nyata, bukan subnet fixture atau perubahan konstanta audit |
| Allowlist publik independen | Kebijakan platform/CDN/redirect eksplisit, DNS/rebinding/private/metadata bypass ditolak melalui jalur kandidat yang sama |
| Binding DNS → IP/socket/firewall | Korelasi pada Linux staging, snapshot A+AAAA lengkap, expiry/revoke/concurrency/controller crash; tanpa resolve kedua |
| TLS jalur produksi | Worker/gateway/egress dan TLS aplikasi dengan identitas produksi, lifecycle/rotasi/revocation, redirect/downgrade dan negatif certificate pada konfigurasi kandidat yang sama |
| Kuota total dan sustained load | Byte/inode mencakup DB/WAL/log/temp/artifact; ENOSPC, restart/crash, cancel dan streaming di bawah beban nyata |
| Pelepasan capability dan kegagalan controller | Inspeksi/runtime proses kandidat deployment, IPC dan controller gagal tertutup; fixture saja belum cukup |

Tambahan wajib: kandidat submission/scheduler/extractor publik yang terintegrasi, ingress TLS/trusted proxy, vulnerability review OS/native/dependency, uji platform yang diizinkan, serta runbook/rollback dan review pemilik. API pengenalan URL dan fixture offline tidak membuktikan extractor publik berfungsi. HD/MP3/rewarded ads masih kandidat terpisah dan bukan alasan melewati gate.

## Tahap berikut yang memerlukan lingkungan berbeda

Pembaruan scope: pemilik kembali memilih tanpa VM. Review pencocokan OS dan alat audit lokal sudah dijalankan, dengan [rencana patch/staging](OS_PACKAGE_REVIEW.md); ini tidak memberikan sign-off paket atau host Linux. Bukti OS baru: outputs/clipora-os-package-review-final.json dan clipora-os-native-linkage.json pada workspace chat.

Sediakan Linux staging terpisah melalui pilihan pemilik, tanpa menyentuh VPS produksi. Jalankan urutan ../clipora_v8_staging_linux/README.md dan kumpulkan bukti enam blocker di atas pada kandidat deployment yang sama. Setelah hasil dan konfigurasi final dapat ditinjau, lakukan sign-off keamanan; persetujuan aktivasi egress/deployment tetap langkah tersendiri. Tidak ada fungsi aktivasi atau sign-off otomatis pada perubahan ini.
