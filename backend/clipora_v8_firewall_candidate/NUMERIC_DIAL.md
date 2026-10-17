# Socket numerik kandidat

NumericDial membuat socket TCP nonblocking dengan keluarga IPv4/IPv6 eksplisit, memvalidasi IP global kanonis dan port 443, memeriksa peer, lalu menyerahkan stream ke Broker. Tidak ada hostname atau fallback alamat. Kegagalan/timeout/cancellation menutup raw socket dan meng-abort transport bila handoff sudah dimulai. Adapter tidak dipasang pada layanan aktif. TLS tetap harus diverifikasi oleh client CONNECT; adapter TCP ini tidak mengklaim verifikasi sertifikat.

## Bukti 17 Oktober 2026

39 tes unit seluruh paket kandidat lulus, termasuk empat tes baru: tujuan invalid ditolak sebelum socket dibuat, cancellation saat connect, timeout connect, dan cancellation selama handoff stream.

run_numeric_wire.py berhasil mentransfer byte melalui Broker dan NumericDial nyata. Tes menggagalkan setiap panggilan getaddrinfo sehingga lookup DNS kedua terdeteksi. Normal exit dan cancellation menutup socket; server menerima EOF; lease simulasi dicabut dan active kembali nol.

Container memakai network=none dan mount bundle minimum readonly. Bootstrap hanya menambahkan 8.8.8.8/32 sebagai alias loopback dalam namespace container disposable serta bind port 443, kemudian membuang seluruh capability dan beralih ke UID/GID 65534 sebelum menjalankan server/probe. Hanya loopback aktif dan memiliki alamat; tidak ada default route. Kernel juga menyediakan interface tunnel placeholder yang down dan tanpa alamat. Tidak ada koneksi ke pemilik IP tersebut di internet. Container tes dihapus. Jaringan/firewall host tidak diubah.

DNS dan firewall pada harness socket masih simulasi. Tes DNS UDP/TCP nyata tersedia terpisah melalui run_dns_wire.py. Belum ada integrasi kernel+DNS+socket+TLS dalam satu runtime, IPC privilege separation, atau uji IPv6 socket nyata. v7, worker offline dan public gate tidak diubah.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -q
.venv/bin/python -B clipora_v8_firewall_candidate/run_numeric_wire.py
```
