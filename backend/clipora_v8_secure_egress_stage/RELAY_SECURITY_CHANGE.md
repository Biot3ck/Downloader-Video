# Clipora — perbaikan lifecycle relay Secure Egress staging

## Masalah dan hasil

Sebelumnya `transfer()` menelan ValueError, timeout, dan error transport. Jika satu arah berhenti akibat batas byte atau idle timeout, relay arah sebaliknya dapat terus menunggu sampai sesi berakhir. Ini menahan resource lebih lama dari yang diperlukan.

`transfer()` sekarang meneruskan kegagalan kepada pemilik sesi. `relay_session()` mengelola kedua task dengan satu anggaran byte dan satu deadline. Saat salah satunya gagal, deadline habis, atau caller membatalkan sesi, kedua task dibatalkan dan ditunggu selesai sebelum handle menutup koneksi. EOF normal tetap mempertahankan half-close agar arah balasan bisa selesai.

## Cakupan

Diubah: `clipora_v8_secure_egress_stage/server_stage.py`.
Ditambahkan: `clipora_v8_secure_egress_stage/test_relay_limits.py` dan catatan ini di direktori staging.

Tidak ada perubahan v7, frontend, worker, firewall, Docker/Compose, VPS, TLS trust, atau DNS policy. Guard deny-all staging dipertahankan. Adapter Secure Egress offline yang sudah ada mengimpor stage ini, sehingga akan menggunakan perbaikan saat proses berikutnya dimulai. Tidak ada server/container yang di-restart oleh pekerjaan ini.

## Bukti pengujian

- Tes regresi pada fungsi transfer lama gagal sebagaimana diharapkan: overflow tidak melempar ValueError.
- Sesudah perbaikan: 14 tes staging lulus (9 tes baru, 5 tes lama).
- Tes baru mencakup anggaran byte gabungan, batas persis, half-close, idle timeout, backpressure timeout, session deadline, pembatalan caller, dan pembatalan task pasangan.
- Tes socket localhost memastikan overflow menutup koneksi client sekaligus upstream. Semua koneksi tes menggunakan 127.0.0.1; alamat 8.8.8.8 hanya nilai sintetik resolver yang dipetakan oleh dial pengganti ke localhost.
- 8 tes API v8 dan 8 tes DNS/SSRF lulus. Total 30 tes lulus pada tahap ini.
- Audit static readiness tetap 26/32 dan NOT READY. Enam gate produksi masih terblokir. Hasil tersebut sebagian merupakan gate yang sengaja di-hardcode gagal, bukan pengukuran runtime.
- Snapshot awal berbeda hanya pada main_v8.py (perubahan UI tahap sebelumnya) dan server_stage.py (perbaikan ini). main.py tetap identik dengan main-v7-stable.py; tidak ada perbedaan sumber lama lainnya.
- Docker E2E belum dijalankan ulang; hasil localhost tidak membuktikan isolasi Linux/container produksi.

## Menjalankan ulang

Dari backend:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_secure_egress_stage -p 'test*.py' -v
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B clipora_v8_ui_baseline/test_ui_api.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s clipora_v8_dns_ssrf_offline/tests -v
.venv/bin/python -B clipora-v8-public-egress-readiness/audit.py --expect-blocked
```

Verifier baseline awal akan melaporkan perubahan server_stage.py sebagai UNEXPECTED CHANGE karena allowlist tahap UI hanya mengenal main_v8.py. Snapshot/allowlist lama sengaja tidak diubah untuk menyembunyikan perbedaan tersebut. Bandingkan patch dan manifest tahap ini untuk meninjau perbaikan yang disetujui.

## Pekerjaan berikutnya

1. Pengujian TLS penuh dengan trust CA fixture yang eksplisit, tanpa `nocheckcertificate=True`; pertahankan fixture lama sampai alternatifnya lulus. Sertifikat fixture lama berakhir 16 Oktober 2026 19:30:46 UTC (22:30:46 Istanbul), sehingga ketergantungan pada sertifikat statis ini perlu dihilangkan.
2. Audit DNS pinning, fallback, dan redirect di jalur worker lengkap.
3. Kuota disk keras serta batas job global.
4. Validasi firewall/isolasi pada Linux terpisah sebelum mempertimbangkan aktivasi public egress. Perubahan VPS dan deployment tetap memerlukan persetujuan.

## Rollback

Kembalikan server_stage.py dari salinan sebelum perbaikan yang disertakan dalam outputs. File tes dan catatan baru boleh dibiarkan; tes regresi baru akan gagal terhadap versi lama. Jangan memulihkan main_v8.py atau frontend saat rollback relay.
