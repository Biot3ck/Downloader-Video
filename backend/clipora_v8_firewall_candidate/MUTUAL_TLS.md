# Identitas gateway melalui TLS mutual pada fixture tiga tier

MutualGateway adalah kandidat transport gateway tanpa listener default. Konfigurasi mengharuskan private IPv4 egress eksplisit, context TLS dengan CERT_REQUIRED dan check_hostname, serta allowlist hostname tujuan. TCP/8888 ke egress memakai TLS dengan server_hostname egress.clipora.test. Request worker HTTP/1.0 dinormalisasi ke HTTP/1.1 hanya untuk CONNECT; parser strict yang ada tetap memeriksa Host, duplicate header, body dan format. Sisa stream diteruskan utuh. Kapasitas/header/idle/byte/session deadline dibatasi. Tidak ada resolusi hostname egress atau fallback transport plaintext yang dipasang.

Mode --mutual pada run_three_tier_kernel.py membuat CA/leaf sementara. Egress mewajibkan sertifikat client, memeriksa tepat satu DNS SAN gateway.clipora.test sebelum membaca CONNECT, dan tetap membatasi source IP gateway serta firewall ingress. Gateway memverifikasi CA/hostname egress. TLS end-to-end worker ke example.com tetap berada di dalam tunnel ini; sertifikat aplikasi masih diperiksa oleh yt-dlp. CA key/CSR/config penerbitan dihapus sebelum runtime bundle dimount. Key gateway tidak disimpan pada bundle egress. Key client lain hanya berada di bundle gateway untuk negative probe fixture, bukan rencana konfigurasi produksi. Seluruh file sementara dihapus pada akhir tes.

Kasus valid melewati worker yt-dlp, gateway TLS mutual, broker/DNS numerik, firewall kernel, TLS aplikasi dan FFmpeg; output MP4 H.264/yuv420p 11528 byte. Saat lease aktif, koneksi tanpa client certificate dan client dengan sertifikat CA valid tetapi DNS SAN other.clipora.test ditolak dari container gateway yang source IP-nya memang diizinkan. Tes ini memisahkan pemeriksaan identitas dari pembatasan jaringan. Tes bypass worker/peer network tetap lulus. Wrong-host dan untrusted-ca pada TLS aplikasi ditolak oleh worker; tidak ada MP4 diekspor. Source IP bukan pengganti autentikasi sertifikat.

Tiga tes unit baru memeriksa context tidak terverifikasi/public egress IP ditolak, normalisasi HTTP/1.0 tidak menelan byte tunnel, serta hostname di luar kebijakan ditolak sebelum koneksi upstream. Total suite kandidat firewall 46 tes unit lulus. Tes tiga tier ini tetap memakai endpoint fixture loopback alias pada egress dan dua jaringan Docker internal di Docker Desktop, bukan internet/platform publik atau host Linux terpisah. Rotasi/revocation/penyimpanan kunci deployment, pengikatan identitas worker ke job, controller crash/restart dan penilaian independen masih diperlukan. Gate public tetap ditutup.

```
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --mutual --case valid
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --mutual --case wrong-host
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --mutual --case untrusted-ca
```
