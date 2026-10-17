# DNS dan socket nyata dalam satu broker

17 Oktober 2026: run_integrated_wire.py menyambungkan SnapshotResolver (dnspython UDP nyata), Broker, dan NumericDial (TCP nyata) dalam satu proses non-root tanpa capability sesudah bootstrap. Transaksi mengirim byte ke server echo dan menerima byte identik. Tidak ada getaddrinfo tambahan; DNS hanya A/AAAA yang diharapkan. Mixed private AAAA dan SERVFAIL keluarga kedua ditolak sebelum grant atau koneksi. Cancellation menutup socket sehingga server menerima EOF; revoke dipanggil dan counter aktif kembali nol.

Harness memakai runner network=none yang sama dengan tes NumericDial; runner menerima probe dan daftar file tambahan eksplisit untuk mengurangi duplikasi. Hanya file bundle yang diperlukan dimount readonly. Bootstrap memasang alias 8.8.8.8/32 ke loopback namespace container; tidak ada akses ke pemilik IP asli. Hanya loopback aktif/beralamat dan tidak ada default route. Kontainer tes milik runner dihapus setelah selesai.

39 tes unit paket kandidat dan kedua harness numeric/integrated lulus setelah perubahan runner. DNS asli di sini berarti paket jaringan nyata ke server fixture loopback, bukan DNS publik atau DNSSEC. Grant/revoke firewall masih objek simulasi. Kernel rule update, privilege-separated IPC, TLS, worker/gateway, serta unduhan platform belum terintegrasi dalam kandidat ini. Tidak ada perubahan web/public gate, v7, atau alur offline worker.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -q
.venv/bin/python -B clipora_v8_firewall_candidate/run_numeric_wire.py
.venv/bin/python -B clipora_v8_firewall_candidate/run_integrated_wire.py
```
