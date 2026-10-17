# Pemeriksaan staging Linux tanpa provisioning

Paket ini hanya menyiapkan kode pemeriksaan. Tidak memasang VM/software, menjalankan SSH, mengubah Docker daemon, menulis konfigurasi jaringan, membuka egress, atau melakukan deployment. Keputusan pemilik untuk tidak memasang VM tetap berlaku.

## Preflight read-only

Dari backend, memakai Python environment yang sudah ada:

```sh
.venv/bin/python -B -m clipora_v8_staging_linux.preflight --state /absolute/existing/private/state --report /absolute/new/preflight.json
```

Direktori state harus sudah ada, dimiliki UID pemanggil, mode tepat 0700, tanpa symlink pada path. Preflight tidak membuat atau mengubahnya. File report baru dibuat 0600; file yang sudah ada tidak ditimpa. Exit 0 berarti host memenuhi pemeriksaan awal untuk fixture, bukan siap produksi. Exit 2 berarti belum memenuhi atau bukti tidak tersedia. Error tulis report juga menghasilkan exit nonzero.

Pada macOS, pemeriksaan berhenti sebelum memanggil Docker: Linux kernel milik Docker Desktop bukan bukti host staging Linux terpisah. Pada Linux, metadata context dibaca tanpa menghubungi daemon; endpoint SSH/TCP/HTTP ditolak. Query daemon dipin ke Unix socket yang diperiksa, dengan override context/host dari environment dihapus untuk query itu. Nama mesin, endpoint, alamat host, environment, atau stderr Docker tidak ditulis ke report.

Pemeriksaan awal meliputi Docker Linux di luar Docker Desktop, seccomp, cgroup v2, direktori state privat, dan filesystem ext4/XFS/Btrfs. Nilai check false berarti syarat belum terbukti; beberapa probe sengaja dilewati pada host yang tidak sesuai. Mount option quota hanya diagnostik: bukan bukti bahwa batas byte/inode telah diterapkan pada state tersebut. Tidak ada test ENOSPC atau perubahan firewall dalam preflight.

## Urutan verifikasi setelah staging tersedia dan disetujui

Gunakan image lokal yang hash-nya sudah diperiksa; jangan pull/build dependency baru tanpa review. Jalankan pada checkout staging terpisah, bukan VPS produksi. Jangan salin .env, token, private key atau seluruh Desktop ke staging.

1. Jalankan preflight. Jika gagal, jangan menandai host layak hanya karena fixture Docker Desktop pernah lulus.
2. Jalankan suite unit web, local_workflow, firewall_candidate, verified_tls dan secure_egress_stage. Simpan log dan commit/hash sumber yang diuji.
3. Jalankan `clipora_v8_firewall_candidate/run_three_tier_kernel.py --mutual --case valid`, `--case wrong-host`, dan `--case untrusted-ca` dari backend dengan Python environment yang sama. Gunakan `--report /absolute/new/<case>.json` yang berbeda per kasus. Harness memakai network internal, fixture HTTPS, sumber worker yang sudah ada, dan cleanup resource miliknya.
4. Jalankan kasus valid `--mutual --cancel-running` dan `-m clipora_v8_local_workflow.run_restart_test /absolute/new/restart.json`. Keduanya hanya fixture lokal. Jangan menjalankan tes crash terhadap preview yang sedang dipakai pengguna.
5. Jalankan `clipora_v8_verified_tls/run_workspace_quota.py /absolute/new/worker-quota.json`. Hasil ini hanya membuktikan tmpfs worker, bukan kuota keseluruhan host.
6. Uji ENOSPC/inode dan cleanup dengan volume staging disposable yang kuotanya disetujui; sertakan DB/WAL/log/temp/artifact, streaming aktif, restart, dan beban berkelanjutan. Preflight tidak menyiapkan atau mengisi volume tersebut.
7. Lengkapi review deployment dan persetujuan aktivasi. Semua langkah di atas tetap offline; tidak mengaktifkan extractor internet.

## Bukti minimum untuk enam blocker audit lama

| Blocker | Bukti yang masih dibutuhkan |
| --- | --- |
| Firewall bukan subnet tes hardcoded | Konfigurasi produksi tervalidasi, topology nyata dan routing IPv4/IPv6 terukur; bukan mengganti konstanta fixture |
| Allowlist publik dengan firewall independen | Kebijakan tiap platform/CDN/redirect; uji bypass worker/gateway/peer, tujuan di luar policy dan rebinding |
| Binding DNS/IP pada host Linux | A+AAAA lengkap, satu snapshot → grant → socket numerik; packet/rule/socket correlation, TTL/expiry dan crash controller pada host staging |
| TLS jalur unduh produksi | Identitas gateway/egress, TLS aplikasi, wrong CA/host/client, rotasi/revocation, downgrade/redirect; fixture mTLS saat ini baru sebagian bukti |
| Kuota disk dan sustained load | Batas byte/inode keseluruhan state, ENOSPC, WAL/temp/log/artifact, admission/cancel/crash/streaming di bawah beban |
| Capability setelah bootstrap | Inspect dan runtime identity/capability pada proses kandidat deployment; kegagalan controller/IPC menutup koneksi |

Audit `clipora-v8-public-egress-readiness/audit.py --expect-blocked` tetap menjadi laporan legacy, bukan scanner produksi lengkap. Jangan mengubah gate statis menjadi true berdasarkan preflight atau fixture. Report baru selalu menyatakan production_ready=false dan public_egress_enabled=false; tidak ada fungsi aktivasi di paket ini.
