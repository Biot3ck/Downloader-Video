# Pembatalan berjalan dan publikasi dengan execution fence

17 Oktober 2026. Perubahan hanya pada kandidat OwnedJobs/API, publisher/observer, dan harness offline; queue/runner v7 dan offline lama tidak diubah.

## State dan otorisasi

Request pembatalan pemilik disimpan pada tabel job_cancellation dalam SQLite. Queue tetap memakai empat state lama sehingga tidak mengubah schema JobStore stabil. Job queued dibatalkan langsung; job processing tetap processing dan tetap memakai slot antrean sampai resource owner memastikan worker/exporter berhenti. Status pemilik mempunyai cancel_requested boolean. Sesi lain tetap mendapat 404 dan tidak dapat meminta pembatalan job asing. Endpoint mengembalikan 204 untuk request idempotent; ini tidak berarti worker sudah mati.

Payload runner hilang setelah cancel, expiry, atau execution fence salah. finish sukses maupun gagal ditolak selama request pembatalan belum diakui lewat confirm_stopped(job_id,execution_owner). Legacy interrupted tanpa fence ditolak untuk OwnedJobs. confirm_stopped hanya API internal trusted, tidak tersedia lewat HTTP. Tidak menerima klaim stop dari browser.

## Observer dan publisher

owned_runner.observe menerima handle resource yang sudah dimiliki, bukan command pengguna. Tidak ada process/Docker launcher atau scheduler otomatis. Handle.stop wajib mengonfirmasi worker DAN exporter benar-benar berhenti. Pembatalan task berulang tidak memutus penantian stop. Stop gagal/tidak terkonfirmasi mempertahankan processing dan execution fence untuk recovery; tidak mengosongkan kapasitas secara prematur. Waktu job dibatasi dan wait observer dibersihkan. Adapter yang mengabaikan kontrak cancellation/stop memerlukan recovery eksternal; modul Python ini bukan batas keamanan terhadap adapter trusted yang berbohong.

owned_publish.publish menyalin regular MP4 bounded 64 MiB ke temporary file 0600 dalam direktori artifact, memegang inode lock, memeriksa ukuran/signature/perubahan sumber dan fsync. Ini tidak menggantikan verifikasi codec/durasi FFmpeg/ffprobe worker. Di dalam transaksi SQLite, fence, sesi, expiry, dan cancellation diperiksa kembali. Hardlink eksklusif memasang inode lengkap tanpa overwrite, fsync direktori dilakukan, lalu state completed di-commit. Request cancel dan publish diserialisasi oleh transaksi: cancel yang commit lebih dahulu menolak publish; publish yang commit lebih dahulu merupakan job selesai dan cancel berikutnya no-op. Kegagalan copy/commit menghapus hanya inode yang dipasang sendiri. Crash sesudah link tetapi sebelum commit tidak memberi akses HTTP karena job masih processing; recovery harus menghentikan resource sebelum mark failed dan sweep.

GC mengenali temporary file privat yang ditinggal dan menghormati lock publisher/stream. Tidak menghapus output processing hanya karena TTL habis. Submission publik dan scheduler publik belum dipasang; observer/publisher tidak dijalankan otomatis oleh preview.

## Bukti

- 51 tes unit web lulus. Tambahan 15 tes mencakup request cancel durable, fence, publication normal, cancel di antara copy/commit, kegagalan commit, ENOSPC, no-overwrite, expiry/deadline, stop gagal, pembatalan berulang, real process stop, owner HTTP, private temp lock, dan legacy interruption yang ditolak.
- Harness Docker --mutual --cancel-running menghentikan worker v8 aktual saat HTTPS metadata fixture ditahan dan lease kernel aktif. Handle memeriksa kedua label owner/job lalu menghapus container menggunakan ID immutable. Hanya sesudah Docker rm selesai job menjadi failed; completion terlambat ditolak; tidak ada MP4 diekspor. Lease kernel akhirnya dicabut. Ini bukan cancellation selama FFmpeg merge; seluruh proses worker memang berada pada container yang dihapus.
- Queue URL pada cancellation harness bersifat sintetis untuk kontrak ownership. Worker tetap memakai URL fixture offline tunggal, bukan YouTube publik. Tidak ada klaim uji extractor platform.
- Regresi --mutual normal menghasilkan MP4 H.264 11528 byte. Kedua surface image web (default dan ownership contract) tetap diuji tanpa published port, readonly/non-root/cap-drop; public download tetap 503. Resource pengujian dihapus, v7 tetap utuh.

```
.venv/bin/python -B -m unittest discover -s clipora_v8_web -p 'test*.py' -q
.venv/bin/python -B clipora_v8_firewall_candidate/run_three_tier_kernel.py --mutual --cancel-running
```

Belum menjadi scheduler publik, belum ada boot/restart recovery yang mengikat ownership store ke seluruh resource produksi, serta belum ada validasi crash OS/disk pada host Linux terpisah. VM tidak dipasang sesuai pilihan pemilik. Gate publik tetap nonaktif.
