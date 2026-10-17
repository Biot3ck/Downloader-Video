# Izin tujuan dinamis pada firewall kernel — offline

`kernel_leases.py` merupakan adapter grant/revoke nyata untuk namespace fixture disposable. Modul ini berada dalam paket kandidat v8 yang sama; bootstrap statis, resolver, v7, runner MP4, dan web staging tidak diubah.

Adapter hanya aktif dengan guard disposable dan konfigurasi `offline-fixture` yang lolos validator lama. Ia menerima Destination immutable untuk hostname sintetis example.com, tepat satu IP privat fixture dan port yang telah dikonfigurasi. Tidak ada profil IP publik, resolver, listener IPC, atau penghubung ke downloader publik. Broker DNS sebelumnya sengaja tetap menolak IP privat; harness kernel membuat Destination fixture secara eksplisit, tanpa mengubah validasi SSRF broker.

## Perilaku

- Awalnya INPUT/OUTPUT/FORWARD IPv4 dan IPv6 DROP. IPv6 tidak memiliki izin tambahan.
- Controller memiliki seluruh filter table namespace fixture. Ruleset IPv4 diganti dengan iptables-restore dan tidak boleh digunakan bersama pengelola firewall lain dalam namespace yang sama.
- Maksimum 32 lease, tiap lease memiliki ID unik. Tujuan IP/port yang sama dideduplikasi pada aturan kernel, tetapi kepemilikan setiap lease tetap terpisah. Revoke satu lease tidak menghilangkan izin tujuan yang masih dipakai lease lain.
- Tidak ada rule ESTABLISHED umum. Izin OUTPUT dibatasi IP/port tujuan dan INPUT reply dibatasi IP/port sumber. Pencabutan lease terakhir menghapus izin di kedua arah, termasuk paket pada flow yang sudah terbuka.
- Grant yang kedaluwarsa atau di luar kebijakan ditolak. Deadline lease ini untuk admission, bukan timer kernel yang otomatis memutus flow. Batas durasi sesi dan pemanggilan revoke tetap kewajiban broker/supervisor.
- Mutasi aturan diserialisasi. Pembatalan, termasuk berulang, menunggu subprocess mutasi yang dibatasi waktunya selesai sebelum lock dilepas. Pemilik transaksi harus tetap menjalankan revoke sesudah pembatalan.
- Bila update gagal, controller mencoba memasang ruleset deny-all dan menjadi poisoned sehingga tidak menerima grant baru. Bila deny-all juga gagal, state lama dipertahankan sebagai unresolved dan error diteruskan. Supervisor harus menghentikan/menghapus namespace itu; modul tidak mengklaim firewall pasti bersih dalam kondisi tersebut.

Ini adalah izin per tujuan pada satu namespace, bukan batas kemampuan satu socket. Proses lain di namespace yang sama dapat memakai tujuan selama ada lease aktif. Pemisahan namespace per job, trust broker/controller, autentikasi IPC, pengawasan crash, dan batas UID perlu diselesaikan sebelum produksi. Administrator Docker host tetap memiliki kuasa atas namespace.

## Bukti kernel aktual

`run_kernel_leases.py` membuat network internal, dua peer TCP, dan controller sementara. Tidak ada port host atau Docker socket yang dipasang. Controller memegang NET_ADMIN serta capability untuk menurunkan privilege child probe; child socket berjalan uid 65534, supplementary groups kosong, semua capability set nol, NoNewPrivs aktif. Controller tidak melayani API jaringan.

Peer positif membuktikan listener tujuan dan port pembanding hidup. Hasil yang lulus:

1. Sebelum grant, koneksi ditolak.
2. Sesudah grant, tujuan yang tepat dapat dihubungi; port lain ditolak.
3. Dua lease ke tujuan yang sama: revoke pertama mempertahankan aliran yang sedang dipakai.
4. Revoke terakhir memblokir koneksi baru dan pertukaran data pada koneksi TCP yang sudah ada.
5. Revoke berulang aman.
6. Ruleset sengaja dibuat merujuk chain yang tidak ada sehingga iptables-restore benar-benar gagal. Fallback deny-all memblokir flow lama dan koneksi baru; grant selanjutnya ditolak oleh controller unhealthy.

Cleanup proses probe memakai penutupan pipe stdin, bukan menambah CAP_KILL. Semua container/network tes dibersihkan melalui nama dan label milik tes. Container sebelumnya tetap ada.

24 tes unit paket lulus (7 adapter kernel baru, 15 binding, 2 policy), mencakup pembatalan berulang saat mutasi, fallback gagal, identitas lease, batas kebijakan, dan deduplikasi tujuan. Tes Docker memakai Linux / Docker Desktop, IP privat sintetis dan TCP echo; belum menguji DNS publik, TLS, IPC, expiry otomatis, atau broker publik bersama adapter ini. Enam gate audit produksi tetap terbuka.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -v
.venv/bin/python -B clipora_v8_firewall_candidate/run_kernel_leases.py /absolute/report.json
```

Langkah berikutnya: desain dan uji pemisahan broker/controller dengan IPC terautentikasi, namespace per job, serta recovery yang menghentikan namespace ketika controller mati. Integrasi tersebut harus menjaga validator alamat publik tetap ketat; pengecualian fixture privat tidak boleh menjadi mode downloader publik.
