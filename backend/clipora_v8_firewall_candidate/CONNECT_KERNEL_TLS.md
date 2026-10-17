# Integrasi offline DNS, broker, kernel, CONNECT dan TLS

Pengujian 17 Oktober 2026 menyatukan resolver DNS paket nyata, Broker, NumericDial, perubahan filter table kernel per lease, CONNECT relay, TLS client, dan HTTP MP4. Semua berjalan dalam satu namespace container network=none dengan alias 8.8.8.8/32 pada loopback. Tidak ada koneksi internet atau perubahan firewall host.

## Implementasi dan batas

connect_relay.py adalah handler tanpa listener CLI. Broker harus dipasang eksplisit; default deny sebelum DNS. Parser CONNECT yang ada dipakai kembali. Kapasitas dibatasi tanpa antrean tunggu; kedua arah berbagi batas byte; pembacaan/penulisan punya idle deadline. Broker mengelola batas sesi serta grant/dial/revoke. Task pump dibatalkan dan ditunggu saat salah satu gagal.

kernel_tls_fixture.py adalah controller pengujian baru, bukan KernelLeases atau controller produksi. Controller hanya menerima JSON melalui satu socketpair SOCK_SEQPACKET yang diwariskan ke child. Tidak ada alamat socket di filesystem atau listener jaringan untuk controller. Child menjadi UID/GID 65534 tanpa capability sebelum membuka DNS/CONNECT/TLS server fixture. Controller root tetap memiliki capability untuk pengubahan aturan pada namespace disposable. Semua izin dan endpoint dibatasi ke example.com:443 / alias loopback 8.8.8.8. IPv6 DROP; komunikasi 127/8 loopback diizinkan untuk fixture DNS dan proxy. Aturan kedua arah untuk server dan client yang berada dalam namespace sama bukan kebijakan produksi tiga tier. Revocation terakhir menghapus aturan TCP tujuan dan tidak mempertahankan general ESTABLISHED.

Client memverifikasi CA dan hostname example.com dengan context CERT_REQUIRED/check_hostname. Tidak ada exception TLS global. CA dan key dibuat sementara, tidak ditambahkan ke trust store host, dan dihapus bersama direktori temporary. Mode salah hostname dan CA tidak dipercaya berhenti sebelum HTTP aplikasi. File MP4 dibuat lokal oleh FFmpeg; body HTTP diterima melalui tunnel dan dibandingkan SHA-256 dengan fixture asli. Tidak ada pengambilan video platform publik.

## Bukti

- 43 tes unit kandidat lulus; termasuk deny default, parser malformed, batas byte, admission, DNS, socket cancellation dan lease.
- Tiga skenario run_integrated_tls.py lulus: TLS valid, salah hostname, CA tidak dipercaya (firewall masih simulasi pada harness itu).
- Tiga skenario run_kernel_tls.py lulus: DNS/socket/TLS nyata dengan firewall kernel fixture dan IPC terpisah.
- Tiga skenario run_connect_tls.py lulus setelah perubahan relay: valid mengirim MP4 identik, dua skenario TLS invalid menolak request HTTP. Sebelum grant dan sesudah revoke, koneksi TCP diblokir kernel. Seluruh counter sesi kembali nol.
- Resource container milik tes dihapus. v7 tidak diubah.

## Belum dibuktikan

Worker yt-dlp dan gateway tiga tier belum memakai jalur ini; fixture memakai client Python dan HTTP server lokal. DNSSEC, autentikasi service antarcontainer, controller crash/SIGKILL dan restart, IPC fault injection, multi-lease/session pada controller fixture, IPv6 nyata, redirect platform, storage quota host, sustained load dan Linux deployment terpisah belum teruji pada gabungan ini. Tidak ada gate produksi yang ditutup. UI/download publik tetap nonaktif. Jangan menjalankan fixture pada host atau network=host, dan jangan menganggap fixture sebagai konfigurasi deployment.

Reproduksi dari backend:

```
.venv/bin/python -B -m unittest discover -s clipora_v8_firewall_candidate -p 'test*.py' -q
.venv/bin/python -B clipora_v8_firewall_candidate/run_integrated_tls.py
.venv/bin/python -B clipora_v8_firewall_candidate/run_kernel_tls.py
.venv/bin/python -B clipora_v8_firewall_candidate/run_connect_tls.py
```
