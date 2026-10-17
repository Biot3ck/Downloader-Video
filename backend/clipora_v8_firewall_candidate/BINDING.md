# Kontrak transaksi tujuan DNS → izin firewall → socket

`binding.py` menambahkan Broker ke paket kandidat firewall yang sama. Tidak mengganti resolver, egress aktif, bootstrap offline, ataupun worker yang sudah bekerja. Tidak ada adapter DNS/firewall/socket live terpasang. Tanpa ketiga adapter eksplisit, permintaan ditolak sebelum DNS.

## Invariant yang diuji

1. Target harus hostname yang diizinkan secara eksplisit dan port 443. Tidak ada wildcard atau turunan domain otomatis.
2. Resolver harus menghasilkan snapshot dengan hostname yang sama, kedua himpunan A/AAAA, serta TTL valid. Semua alamat divalidasi, termasuk alamat yang tidak dipilih. Alamat private/metadata/reserved/multicast, keluarga IP yang salah, IPv4-mapped IPv6, scope ID, field hilang, dan TTL invalid ditolak. Adapter resolver kelak harus meneruskan kegagalan NXDOMAIN/timeout, bukan menyamarkannya sebagai himpunan kosong.
3. Snapshot disalin menjadi tuple immutable. IP dipilih sekali; broker tidak resolve ulang. TTL izin memulai koneksi maksimum 30 detik, dihitung konservatif sejak permintaan DNS dimulai. Izin dicek sesudah DNS, sesudah grant, dan sesudah dial.
4. Objek Destination yang sama, dengan lease ID unik, dikirim ke grant dan revoke; dial hanya menerima IP numerik dan port dari objek tersebut. Peer socket harus cocok sebelum stream diberikan ke pemakai.
5. Paling banyak delapan transaksi aktif per instance/event loop; ini bukan batas global lintas proses. Tidak ada antrean tunggu tanpa batas. DNS, grant/dial, sesi, dan cleanup memiliki timeout. Batas sesi default 90 detik, terpisah dari TTL untuk memulai koneksi.
6. Pada sukses, exception, timeout, atau pembatalan, socket ditutup dan revoke tetap dicoba, termasuk grant yang mungkin gagal sesudah memasang sebagian aturan. Revoke harus idempotent. Kegagalan penutupan socket atau revoke membuat broker menolak transaksi baru sampai recovery eksternal.

## Kewajiban adapter berikutnya

- Resolver: A dan AAAA lengkap, deadline/capacity, TTL konservatif, tanpa fallback tersembunyi setelah error. Allowlist hostname/CDN/redirect perlu ditinjau untuk tiap platform.
- Firewall: grant berbasis objek tujuan tervalidasi; identitas lease tidak boleh tertukar; revoke idempotent, aman bila grant belum terjadi, dan tidak mencabut izin koneksi lain. Adapter harus menghormati cancellation. Izin ESTABLISHED dan flow yang telah terbuka memerlukan lifecycle yang eksplisit; bootstrap statis saat ini belum menjadi adapter grant/revoke.
- Socket: dial numerik tanpa lookup hostname, cleanup socket internal bila dial dibatalkan sebelum writer dikembalikan, serta peername asli tanpa pemetaan/pemalsuan.
- Runtime: pemisahan privilege, autentikasi IPC broker/controller, recovery aturan setelah crash, kebijakan untuk sesi lain ketika broker unhealthy, serta attestation Linux. Broker ini bukan batas keamanan terhadap kode Python lain yang dapat mengganti adapter dalam proses yang sama.

## Bukti dan batas

15 tes transaksi baru serta dua tes kebijakan firewall yang ada lulus di Python host dan Python container Linux. Container tes memakai network none, readonly, non-root, cap-drop ALL, NoNewPrivs, serta mount hanya modul tes/validator yang diperlukan.

Skenario: deny sebelum DNS; immutable snapshot; mixed public/private A/AAAA; snapshot hilang/invalid; DNS timeout; hostname tidak diizinkan; TTL sebelum/sesudah grant; grant parsial gagal; peer socket salah; revoke gagal; pembatalan sesi/grant; batas kapasitas; timeout sesi/grant/revoke; kegagalan close; dan dua koneksi ke IP sama dengan lease berbeda.

Adapter dalam tes adalah objek simulasi. Ini belum membuktikan aturan kernel dipasang per lease, DNS resolver nyata, atau unduhan TLS melalui broker. Suite firewall namespace sebelumnya membuktikan aturan kernel statis secara terpisah. Kedua bukti belum boleh digabung menjadi klaim integrasi produksi. Public egress tetap nonaktif dan audit produksi tetap blocked.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -v
```

## Perbaikan pembatalan berulang

Cleanup broker kini tetap dilindungi pada setiap pembatalan task, sampai close/revoke selesai atau menghasilkan error melalui timeout adapter. Sebelumnya pembatalan kedua dapat diteruskan ke task cleanup dan mengganggu revoke. Tes regresi mereproduksi kegagalan itu sebelum perbaikan. Tes kedua memastikan kegagalan revoke tetap terlihat dan memblokir transaksi baru meskipun task dibatalkan berulang. Ini pengujian unit tanpa jaringan; tidak membuktikan integrasi broker dengan kernel atau recovery setelah proses mati.
