# Hasil spike yang tercatat

Laporan mentah per URL sengaja **tidak** di-commit: `hasil/` berisi tautan pihak ketiga dan
diabaikan oleh `.gitignore`. Berkas ini menyimpan ringkasan yang menjadi dasar keputusan
[ROADMAP 4.4](../../ROADMAP.md), tanpa URL.

## 18 Oktober 2026 — GitHub Actions (Azure)

80 URL (20 per platform), yt-dlp 2026.08.19. Ini **batas bawah**: IP Azure dipakai bersama,
bukan VPS khusus. Lihat `README.md` untuk peringatan yang sama.

### Mode default — egress `4.149.237.36`

| Platform | Diuji | Berhasil | Success rate |
| --- | ---: | ---: | ---: |
| TikTok | 14 | 0 | 0% |
| Instagram | 13 | 13 | 100% |
| Pinterest | 2 | 2 | 100% |
| YouTube | 20 | 0 | 0% |

- URL mati/privat (tidak dihitung): Pinterest 1.
- Post hanya gambar (diukur terpisah): TikTok 6, Instagram 7, Pinterest 17.
- Kegagalan TikTok: `Unexpected response from webpage request` pada semua 14 URL.
- Kegagalan YouTube: `Sign in to confirm you're not a bot` pada semua 20 URL.

### `--impersonate chrome` — egress `20.55.162.193`

| Platform | Diuji | Berhasil | Success rate |
| --- | ---: | ---: | ---: |
| TikTok | 14 | 14 | **100%** |
| Instagram | 13 | 13 | 100% |
| Pinterest | 2 | 2 | 100% |
| YouTube | 20 | 0 | 0% |

Keputusan otomatis kriteria 4.3: **LANJUT**.

### YouTube per client — 20 URL, `--impersonate chrome`

| Client (`youtube:player_client`) | Berhasil |
| --- | ---: |
| `android_vr` | 0/20 |
| `tv` | 0/20 |
| `web_embedded` | 0/20 |

Ketiganya gagal dengan pesan yang sama (`Sign in to confirm you're not a bot`), jadi masalahnya
bukan pilihan client. Tanpa cookie/PO token tidak ada jalur sah dari IP datacenter; lihat
ROADMAP 4.4 untuk keputusan menangguhkan YouTube dari janji publik.

## Membuat hasil baru

```bash
cd backend
.venv/bin/python -B -m clipora_v8_spike.spike \
  --urls clipora_v8_spike/urls.txt --out ../hasil-spike.csv
```

Laporan `.md` dan `.csv` ditulis di samping `--out`. Setelah membaca angkanya, perbarui tabel di
berkas ini (tanpa URL) bila hasilnya mengubah keputusan.
