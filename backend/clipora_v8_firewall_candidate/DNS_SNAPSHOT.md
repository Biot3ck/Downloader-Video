# Resolver DNS untuk broker kandidat

SnapshotResolver menerima callable dnspython async Resolver.resolve yang dikonfigurasi secara eksplisit. Tanpa callable, akses ditolak sebelum kueri. Tidak ada pemasangan otomatis pada web, worker, atau egress aktif.

Adapter menanyakan A dan AAAA dengan search=False dan nama absolut. Kedua keluarga harus selesai; NXDOMAIN/SERVFAIL/timeout membatalkan seluruh hasil. Semua IP diperiksa ulang oleh validator broker sebelum grant. Alias kedua keluarga harus konsisten. Deadline total dan kapasitas per instance membatasi pekerjaan, termasuk cancellation. TTL memakai minimum rantai CNAME, sisa expiration Answer (termasuk cache), maksimum 30 detik, dan pengurangan konservatif waktu kueri. Broker memvalidasi snapshot kembali.

## Verifikasi 17 Oktober 2026

35 tes unit paket kandidat lulus. Sembilan tes adapter mencakup jawaban lengkap, TTL/alias/cache, private/mixed address, error keluarga kedua, kapasitas, pembatalan dan timeout.

run_dns_wire.py menguji dnspython nyata melalui paket UDP dan fallback TCP ke server loopback. Container network=none, readonly, non-root, cap-drop ALL dan NoNewPrivs. Kasus safe, truncated, CNAME, private, mixed AAAA, NXDOMAIN, SERVFAIL dan TTL nol lulus. Container milik tes dihapus setelah selesai.

Firewall grant/revoke serta dial media pada tes wire masih simulasi. Hasil ini bukan bukti integrasi kernel, TLS, downloader, DNSSEC, firewall DNS, atau download platform publik. Konfigurasi deployment harus membatasi server/rute DNS dan memverifikasi tanpa fallback di luar kebijakan. Enam gate produksi lama tidak ditutup oleh suite ini.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -v
.venv/bin/python -B clipora_v8_firewall_candidate/run_dns_wire.py
```

Referensi API: https://dnspython.readthedocs.io/en/stable/async-resolver-class.html dan https://dnspython.readthedocs.io/en/stable/resolver-class.html (dnspython 2.9.0 diperiksa).
