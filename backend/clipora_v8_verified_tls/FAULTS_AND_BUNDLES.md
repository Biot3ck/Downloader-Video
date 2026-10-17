# Worker minimal dan pengujian gangguan proses

Worker offline terverifikasi memakai bundle sementara berisi tujuh modul runtime backend dan worker_verified.py. Direktori backend penuh tidak lagi di-mount pada runner ini. Services hanya mendapat gateway.py, egress_fixture.py, dan fixture video; kebijakan stage disalin dari tujuh file yang disebut eksplisit. File lain, termasuk .env, database, arsip, serta private key di direktori sumber, tidak ikut tersalin. Input symlink ditolak. Ini pembatasan akses mount, bukan audit keamanan isi seluruh image atau modul runtime.

/app dan /trust tetap readonly. Collector memeriksa mount Docker aktual: hanya dua bind tersebut, tanpa bind tambahan; /app harus menunjuk bundle yang diharapkan. Path macOS dinormalisasi pada kedua sisi sebelum dibandingkan. /output dan /tmp tetap tmpfs terbatas, root readonly, jaringan internal, dan TLS diverifikasi. Compose asli tidak diubah: overlay sementara mengganti volume berdasarkan target, lalu collector memverifikasi hasil aktual.

## Pengujian

- 35 tes unit/kontrak/delivery/staging/bundle, 25 DNS/relay, dan 8 API: 68 lulus.
- Delapan kasus TLS/redirect memakai Docker aktual lulus setelah perubahan mount.
- Job Compose aktual melalui FastAPI menghasilkan fixture MP4 identik; status persisten dan Range 206 tetap bekerja setelah lifecycle dibuka kembali. Public download tetap 503.
- run_process_faults.py menjalankan dua skenario SIGKILL terhadap proses Python disposable saat Docker worker aktual telah dimulai. Wrapper khusus tes menahan collector agar titik gangguan dapat diulang, tanpa hook pada kode produksi.
- Parent dimatikan: runner anak tetap memegang flock; dispatcher lain tidak boleh menjalankan job kedua. Setelah anak berhenti, recovery menandai job pertama gagal dan job penerus Compose aktual selesai.
- Runner dimatikan: parent membersihkan resource Docker berlabel milik job itu dan menandainya gagal. Job penerus Compose aktual selesai. Artifact job terputus tidak ditawarkan sebagai completed.
- run_queue_burst.py: empat putaran masing-masing 12 proses independen mengirim job bersamaan. Setiap putaran menerima tepat empat dan menolak delapan. Antrean dikosongkan setelah tiap burst. Ini tes admission SQLite, bukan benchmark throughput video atau jaminan kapasitas produksi.

Tes memakai SQLite, staging, sertifikat, dan resource Docker sementara. Docker daemon tidak dihentikan. Container lama tidak dihapus. State web pengguna tidak dimigrasi/dimulai ulang; tidak ada deployment atau perubahan VPS.

## Batas dan langkah berikutnya

Pengujian SIGKILL membuktikan recovery pada runner lokal macOS/Docker Desktop dengan direktori state bersama; belum menguji host mati/reboot, daemon Docker crash, filesystem penuh pada host, atau multi-host. Job interrupted gagal dan perlu permintaan baru, tanpa retry otomatis. Tidak ada klaim public egress siap produksi.

Prioritas berikut: bukti isolasi/firewall pada lingkungan Linux disposable yang setara produksi, kemudian penutupan enam blocker audit public egress. Public internet download tetap dinonaktifkan sampai blocker diselesaikan dan aktivasi disetujui. Tahap ini tidak mengubah v7, modul worker bersama, ataupun konfigurasi Compose asli.
