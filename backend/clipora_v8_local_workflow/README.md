# Alur produk lokal Clipora

Launcher ini menghubungkan UI Clipora ke antrean durable, worker Docker aktual, gateway/egress mTLS, MP4 terverifikasi, dan unduhan milik sesi browser. Hanya video sampel tetap dari fixture jaringan internal yang diproses. Endpoint tidak menerima URL atau perintah pengguna. Ini bukan unduhan YouTube/TikTok/Instagram/Pinterest dan bukan mode deployment publik.

## Menjalankan

Dari direktori backend dengan Docker Desktop dan image fixture lokal yang sudah tersedia:

```sh
.venv/bin/python -B clipora_v8_web/run_local.py --offline-workflow --port 8090 --state /absolute/private/state
```

Server hanya bind 127.0.0.1. Tanpa flag tersebut, launcher tetap membuka UI biasa tanpa scheduler Docker. Image web staging juga tidak menyertakan paket launcher ini atau Docker socket. Jangan memasang Docker socket ke container web publik.

Klik **Prepare sample**, tunggu progres, lalu preview atau **Download sample**. Refresh mempertahankan hasil melalui ID job dalam sessionStorage dan cookie HttpOnly. Cookie sesi valid digunakan kembali; token tidak tersedia untuk JavaScript. Pembatalan menunggu worker/exporter berhenti dan resource terhapus sebelum melepaskan kapasitas. Permintaan URL publik tetap 503.

## Recovery dan batas

Satu scheduler memegang flock; helper mewarisi file descriptor agar restart tidak berlomba dengan proses ekspor setelah web mati. Jika helper masih hidup, startup scheduler kedua ditolak; tunggu helper selesai lalu jalankan ulang launcher. Recovery menghapus resource berdasarkan execution owner dan ID Docker immutable, menandai processing lama gagal, tanpa retry otomatis. Hasil parsial tidak dipublikasikan. Resource Docker lain tidak disentuh.

Hanya satu job berjalan, maksimal empat aktif, satu per sesi. MP4 dibatasi 64 MiB, TTL job satu jam, sesi 24 jam. Sweep berjalan saat idle dan permintaan sesi; lock streaming melindungi file yang sedang dibaca. Batas ini belum menggantikan kuota filesystem host untuk artifact/DB/WAL/log. Host launcher mempunyai akses Docker dan khusus pengembangan lokal tepercaya.

## Bukti pengujian

- Enam tes kontrak local workflow dan 51 tes web (ownership, cancellation, publisher, streaming).
- HTTP aktual: queued → processing → completed; H264 MP4 11.528 byte, Range, penolakan sesi asing, session reuse, public 503.
- Pembatalan HTTP saat worker aktual aktif: stop dan cleanup selesai, tidak ada file.
- SIGKILL web disposable saat helper aktif: leadership tetap terkunci, recovery gagal aman tanpa duplikasi, work sementara bersih.
- Browser aktual: hasil selesai tetap tersedia setelah refresh; media dan tautan unduh muncul.

Laporan berada di folder outputs chat. Jangan mengganti blocker release berdasarkan sampel offline. Staging Linux terpisah, kuota/load/chaos, kebijakan domain/CDN/redirect, review dependency/OS, dan verifikasi empat platform masih wajib sebelum persetujuan egress/deployment. Pemilik menolak instalasi VM dalam sesi ini; tidak ada VM/VPS yang diubah.

## Sampel album gambar

Mode Images / album kini menyediakan Prepare sample album. Endpoint lokal /api/v8/samples/images hanya menerima objek kosong; scheduler dispatch hanya payload fixture gambar yang tetap, di samping fixture video lama. Album berbagi antrean, pemilik, leader lock, cancellation dan GC dengan video. Gambar/ZIP dipublikasikan setelah worker berhenti, kemudian read route owned menyajikan manifest/berkas; tidak memakai route MP4. Lihat ../clipora_v8_image_backend/README.md. Default launcher/image web tanpa flag ini tidak memuat endpoint sampel atau launcher Docker. Public URL payload gambar juga ditolak oleh scheduler lokal.
