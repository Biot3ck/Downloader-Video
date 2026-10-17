# Bootstrap firewall v8 — kandidat offline

Modul ini terpisah dari egress aktif, v7, dan runner MP4 offline yang sudah bekerja. Belum terintegrasi dengan downloader publik dan tidak boleh menjadi dasar mengaktifkan public egress.

`policy.py` menerima hanya mode `offline-fixture`, subnet RFC1918 /16 sampai /29, gateway dan tujuan IPv4 numerik di subnet itu, satu port TCP tinggi, serta uid/gid non-root. Field tambahan, alamat ambigu, credential, IP metadata, IP publik, endpoint subnet, port non-integer, dan mode public ditolak. Tidak ada rule DNS/UDP/QUIC atau izin IPv6.

`bootstrap.py` memasang DROP pada INPUT/OUTPUT/FORWARD IPv4 dan IPv6 sebelum memvalidasi konfigurasi. Ruleset baru dipasang dengan iptables-restore/ip6tables-restore. Hanya gateway yang boleh membuka TCP 8888 dan hanya IP/port fixture yang boleh menjadi tujuan koneksi baru. Reply ESTABLISHED diizinkan. Tidak ada flush firewall host; harness memakai namespace container sendiri dengan jaringan internal.

Bootstrap sementara membutuhkan NET_ADMIN, SETPCAP, SETUID, SETGID. Sesudah aturan terpasang, proses mengaktifkan NoNewPrivs, mengosongkan seluruh bounding capability, menghapus supplementary groups, mengganti gid/uid, memverifikasi semua capability set nol, lalu exec layanan. Kegagalan menghentikan startup. Operator Docker host tetap memiliki kuasa atas container; pelepasan capability ini membatasi proses layanan, bukan administrator Docker.

## Bukti

`run_offline.py` menggunakan image lokal, jaringan internal acak, peer TCP sintetis dan container disposable. IP/port yang diblokir memiliki listener aktif yang diuji dari peer lain sehingga kegagalan koneksi bukan karena layanan target mati. Hasil: koneksi sesuai rule berhasil; IP lain, port lain dan sumber inbound lain ditolak; layanan tidak bisa mengubah firewall dan rule tetap berlaku sesudah percobaan itu. Semua capability set nol dan uid/gid 65534. Konfigurasi invalid dan ketiadaan NET_ADMIN mencegah layanan mulai. Cleanup hanya nama/label milik tes; container lama dipertahankan.

Ini belum membuktikan binding DNS publik dinamis, rotasi/expiry izin, transfer TLS melalui kandidat ini, firewall host produksi, kegagalan daemon/reboot, atau kuota staging host. Enam gate audit produksi tetap terbuka. Tidak ada klaim bahwa hasil offline ini membuat egress siap publik.

Jalankan dari backend:

```
.venv/bin/python -B -m unittest clipora_v8_firewall_candidate.test_policy -v
.venv/bin/python -B clipora_v8_firewall_candidate/run_offline.py /absolute/report.json
```
