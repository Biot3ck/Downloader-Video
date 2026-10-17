# Worker, gateway dan egress pada namespace terpisah

Pengujian offline 17 Oktober 2026 menjalankan worker v8 yang ada tanpa modifikasi, gateway fixture lama dalam container tersendiri, serta DNS/broker/kernel-controller/TLS fixture dalam container egress. Ada dua Docker network internal: worker-network hanya worker dan gateway, egress-network hanya gateway dan egress. Container attacker sementara di egress-network digunakan untuk tes penolakan sumber lain. Network topology diverifikasi melalui Docker inspect. Worker tidak lagi berbagi namespace egress dalam harness ini.

## Batas kebijakan fixture

three_tier_fixture.py adalah controller offline terpisah. Config hanya mode offline-three-tier dan subnet RFC1918 terbatas; IP gateway/egress harus berbeda dalam subnet yang sama. Host harness memilih alamat statis pada network baru miliknya; tidak memakai alamat dari container belum start (Docker belum mengisi IPAddress saat create). Egress memverifikasi alamat eth0 dan tidak adanya default IPv4 route melalui /proc/net/route. BusyBox ip route show default dapat mencetak connected route, sehingga bukan alat pemeriksaan default route yang dipakai.

Controller hanya menerima lease example.com:443 -> 8.8.8.8/32 yang merupakan alias loopback lokal. INPUT pada eth0 mengizinkan TCP/8888 dari tepat IP gateway, OUTPUT pada eth0 hanya balasan ESTABLISHED ke IP itu dengan source port 8888. IPv6 seluruhnya DROP. Port 443 hanya diizinkan pada loopback saat lease aktif; aturan dihapus saat revoke. DNS memakai server fixture loopback, bukan resolver internet. Tidak ada route publik atau koneksi ke pemilik IP 8.8.8.8 asli.

Service child turun ke non-root dan capability nol sebelum memuat server. Controller root mempunyai capability firewall untuk namespace container disposable. IPC adalah socketpair yang diwariskan, tanpa listener network/filesystem. Pemeriksaan source IP tambahan dilakukan sebelum CONNECT parser. IP bukan autentikasi kriptografis; service identity produksi tetap pekerjaan terpisah.

## Hasil

- Kasus valid: yt-dlp/FFmpeg worker menghasilkan MP4 11528 byte, H.264/yuv420p diverifikasi ffprobe melalui actual gateway -> CONNECT -> DNS -> broker -> kernel firewall -> socket numerik -> TLS.
- Sesi valid sengaja ditahan sebelum respons HTTP fixture. Saat aturan port 443 masih aktif, worker gagal menghubungi egress TCP/8888 secara langsung, alias global port 443, dan metadata 169.254.169.254:80. Gateway gagal menghubungi port TLS egress secara langsung. Peer lain yang benar-benar berada pada egress-network gagal menghubungi TCP/8888 egress. Aturan aktif dicek sebelum dan sesudah probe. Setelah probe, runner melepas barrier melalui tmpfs /control yang hanya ada pada fixture egress.
- Wrong-host dan untrusted-ca: yt-dlp menolak sertifikat, tidak ada MP4 diekspor. Tes bypass saat lease aktif tidak diulang pada kasus negatif (field JSON null berarti tidak diuji).
- Aturan tujuan dicabut sesudah worker selesai/gagal; IPv6 OUTPUT tetap DROP. Semua container/network milik tes dihapus dan container yang sudah ada dipertahankan.
- 43 tes unit kandidat lulus. Harness namespace-sharing lama juga diuji ulang setelah perubahan service dan tetap lulus.

## Batas penerimaan

Ini bukti integrasi offline di Linux container Docker Desktop, bukan attestation deployment Linux terpisah. Endpoint HTTPS masih fixture dalam namespace egress sendiri, bukan server publik terpisah. Gateway adalah fixture, tidak ada autentikasi service kriptografis. IPC fault/crash/restart, expiry lease saat controller mati, sustained load, kuota filesystem host, IPv6 socket nyata, redirect/CDN/empat platform dan extractor publik belum diterima. Scope unit policy lama dan hardcoded gate audit tidak diubah. UI dan download publik tetap nonaktif; v7 dan runner offline stabil tidak dimodifikasi.

Reproduksi dari backend:

```
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --case valid
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --case wrong-host
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --case untrusted-ca
```
