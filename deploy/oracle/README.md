# Deploy staging di Oracle Cloud Always Free

Panduan ini memasang **kandidat deployment** Clipora di VM ARM Oracle Cloud.
Tujuannya menutup enam bloker rilis di host Linux nyata, bukan membuka unduhan
publik. Gerbang publik tetap tertutup.

Ringkasan kapasitas Always Free per Oktober 2026: **2 OCPU / 12 GB RAM** untuk
Ampere A1 (dipotong dari 4/24 pada Juni 2026), 200 GB block volume, dan
**10 TB egress/bulan** di home region. 10 TB menutup sekitar 1.000 unduhan/hari
(±468 GB/bulan pada 12 MB per unduhan), jadi bandwidth bukan kendala awal.

> Status: skrip dan compose di folder ini belum pernah dijalankan di OCI. Mereka
> disusun dari konfigurasi yang sudah diuji lokal (image, container, gate).
> Perlakukan langkah verifikasi di bawah sebagai bagian wajib dari deployment.

## 1. Akun dan region

1. Daftar di <https://www.oracle.com/cloud/free/>. Kartu diperlukan untuk
   verifikasi; resource Always Free tidak menagih.
2. Pilih **home region** yang dekat pengguna dan punya kapasitas A1. Untuk
   Indonesia: `ap-singapore` atau `ap-jakarta` bila tersedia. Home region tidak
   bisa diubah setelah akun dibuat.
3. Tunggu sampai akun selesai diprovision (biasanya beberapa menit).

## 2. Jaringan

Di OCI Console: **Networking → Virtual Cloud Networks → Create VCN**.

- Pilih **Create VCN with Internet Connectivity**.
- Nama: `clipora-vcn`. CIDR `10.0.0.0/16`, public subnet `10.0.0.0/24`.
- Setelah dibuat, buka **Security Lists → Default Security List** dan tambah
  ingress:

| Source | Protocol | Port | Keterangan |
| --- | --- | --- | --- |
| `0.0.0.0/0` | TCP | 80 | ACME HTTP-01 dan redirect |
| `0.0.0.0/0` | TCP | 443 | HTTPS |
| `0.0.0.0/0` | UDP | 443 | HTTP/3 (opsional; TCP tetap bekerja) |
| IP Anda | TCP | 22 | SSH, jangan dibuka ke semua |

Bila memakai IPv6, tambahkan aturan yang sama untuk `::/0` dan aktifkan IPv6
pada VCN/subnet.

## 3. Instance

**Compute → Instances → Create instance**.

- Nama: `clipora-staging`.
- Image: **Canonical Ubuntu 24.04** (arsitektur aarch64).
- Shape: **Ampere → VM.Standard.A1.Flex**, 2 OCPU, 12 GB.
- Boot volume: 50 GB.
- Networking: VCN `clipora-vcn`, public subnet, **Assign a public IPv4 address**.
- SSH keys: unggah public key Anda.
- Create.

Bila muncul *out of capacity*, coba availability domain lain atau ulangi nanti.
Jangan turun ke shape micro: FFmpeg dan dua unduhan bersamaan butuh memori lebih.

## 4. DNS

Tambahkan record A dari hostname staging ke public IPv4 instance. Contoh:

```
staging.clipora.example.  300  IN  A  203.0.113.10
```

Jika memakai Cloudflare, matikan proxy (grey cloud) sampai sertifikat diperoleh,
lalu aktifkan lagi dengan mode **Full (strict)** bila mau. Caddy memerlukan port
80 dan 443 langsung untuk ACME.

Cek dari komputer Anda:

```sh
dig +short A staging.clipora.example
```

## 5. Provision host

Dari komputer Anda:

```sh
scp deploy/oracle/provision.sh ubuntu@<IP>:/tmp/provision.sh
ssh ubuntu@<IP> 'sudo bash /tmp/provision.sh'
```

Skrip memasang Docker + Compose, membuat `/opt/clipora/{src,data}`, membatasi
log Docker/journal, membuka 80/443 di firewall host (image Ubuntu OCI menolak
semua kecuali SSH secara default), dan mematikan login SSH berbasis password.

Setelah selesai, keluar dan masuk lagi agar keanggotaan grup `docker` aktif.

## 6. Deploy aplikasi

Salin repo dari akar proyek:

```sh
rsync -az --delete \
  --exclude '.git' --exclude '.venv' --exclude '*_runtime' \
  --exclude '.playwright-mcp' --exclude 'node_modules' \
  ./ ubuntu@<IP>:/opt/clipora/src/
```

Di server:

```sh
cd /opt/clipora/src/deploy/staging
cp .env.example .env
sed -i 's/^CLIPORA_DOMAIN=.*/CLIPORA_DOMAIN=staging.clipora.example/' .env
docker compose up -d --build
```

Build pertama mengunduh base image, FFmpeg, dan wheel ber-hash; butuh beberapa
menit. Setelah selesai, Caddy meminta sertifikat untuk domain tersebut.

## 7. Verifikasi

```sh
docker compose ps
curl -s https://staging.clipora.example/healthz
curl -sI https://staging.clipora.example/ | grep -iE 'strict-transport|content-security|x-frame|server'
curl -s -o /dev/null -w '%{http_code}\n' \
  -X POST https://staging.clipora.example/api/v8/download \
  -H 'Origin: https://staging.clipora.example' \
  -H 'Content-Type: application/json' -d '{}'
```

Yang harus terlihat:

- `/healthz` → `public_downloads_enabled: false`, `ready_for_public_launch: false`,
  `real_downloads_enabled: false`;
- HSTS dan CSP ada, header `Server` tidak ada;
- `POST /api/v8/download` → **503**;
- sertifikat diterbitkan Let's Encrypt (cek dengan `curl -vI`).

Uji ekstraksi nyata lewat tunnel loopback (route nyata hanya aktif untuk origin
loopback):

```sh
# di server
cd /opt/clipora/src/deploy/staging
docker compose -f compose.yaml -f compose.real-test.yaml --profile real-test up -d real-test

# di komputer Anda
ssh -N -L 8091:127.0.0.1:8091 ubuntu@<IP>
```

Buka `http://127.0.0.1:8091`, tempel tautan TikTok, lalu unduh video/MP3.
Setelah selesai, matikan:

```sh
docker compose -f compose.yaml -f compose.real-test.yaml --profile real-test down
```

Untuk bukti yang bisa diulang (bukan hanya klik manual), jalankan smoke test dari
komputer Anda lewat tunnel yang sama:

```sh
python3 deploy/staging/smoke_real.py --base-url http://127.0.0.1:8091 \
  --workdir /tmp/clipora-smoke --hd
```

Skrip keluar `0` hanya bila preview, Range `206`, MP4, HD, MP3, dan gerbang
`503` semuanya benar. Simpan output JSON-nya sebagai bukti deployment.

## 8. Operasi

```sh
docker compose logs -f --tail=100          # log web + caddy
docker compose restart web                 # restart aplikasi
docker compose up -d --build               # setelah rsync kode baru
docker compose down                        # hentikan, volume tetap ada
```

State aplikasi hanya cache media dan database limiter di volume
`clipora-staging_state`; tidak ada data pengguna. Volume `caddy_data` menyimpan
sertifikat, jangan dihapus sembarangan (rate limit ACME).

## 9. Batasan dan biaya

- **Idle reclamation**: instance Always Free yang idle (CPU/network/memori
  rendah) selama 7 hari dapat direklamasi. Host staging yang sepi berisiko.
  Opsi: jaga aktivitas, atau upgrade akun ke Pay As You Go — resource Always
  Free tetap gratis, tetapi tidak lagi direklamasi karena idle.
- **Bandwidth** adalah biaya utama produk ini. 10 TB/bulan cukup untuk tahap
  awal; begitu trafik naik, pindah ke VPS berbayar lebih murah daripada
  melanggar kuota.
- **YouTube** tidak dijanjikan: 0/20 dari IP datacenter. Jangan tampilkan di UI
  publik sebelum ada solusi yang sah.
- **Gerbang publik** tetap tertutup sampai enam bloker di
  `backend/clipora_v8_web/docs/RELEASE_SECURITY.md` ditutup.

## 10. Troubleshooting

| Gejala | Penyebab umum | Tindakan |
| --- | --- | --- |
| `Out of capacity` saat create | A1 penuh di AD itu | Coba AD lain, ulangi nanti |
| Port 80/443 tidak terjangkau | Security list VCN atau iptables host | Cek keduanya; `sudo iptables -S INPUT` |
| Caddy gagal ambil sertifikat | DNS belum mengarah, port 80 tertutup, atau rate limit | `docker compose logs caddy`; cek `dig` |
| `503 Request admission is temporarily unavailable` | `/data` bukan mode 0700 / bukan UID 10001 | `sudo ls -ld /opt/clipora/data`; pakai volume, bukan bind mount yang salah owner |
| `400 Invalid host` | `CLIPORA_DOMAIN` tidak sama dengan Host | Samakan `.env` dan DNS |
| `403 Same-origin request required` | Origin tidak sama persis (skema/host/port) | Pastikan diakses lewat `https://` domain yang sama |
| TikTok gagal 100% | `curl_cffi` tidak terpasang | `docker exec ... python -c 'import curl_cffi'` |
| Healthcheck `unhealthy` | Aplikasi gagal start | `docker compose logs web` |
