# Panduan Langkah-Langkah Pembuatan Sistem (Bahan Laporan Ketentuan No. 4)

Sesuai **Ketentuan Final Project IAK No. 4**:
> *"Laporan memuat langkah-langkah yang dilakukan dalam pembuatan sistem, bukan hanya screenshot hasil."*

Berikut urutan langkah teknis pembuatan Sistem HRM Kelompok 12 yang dapat langsung dijadikan kerangka penulisan laporan (lengkap dengan bagian yang perlu diambil screenshot-nya):

---

## Langkah 1: Analisis Kebutuhan Proses Bisnis & Pemetaan Integrasi
1. Mengidentifikasi ruang lingkup modul HRM sesuai 3 tema studi kasus UAS (**Software**, **Manufaktur**, dan **Telekomunikasi**) dengan fitur manajemen profil perusahaan dinamis (`company_profile`).
2. Memetakan titik pertukaran data (*integration touchpoints*) antara **Kelompok 12 (HRM)** dengan 3 komponen perusahaan lainnya:
   - **HRM ↔ CRM (Kel. 7):** HRM menyediakan master staf sales (`CRM_SALES`); CRM menyediakan data komisi & jumlah *closing deal* per periode untuk komponen *payroll*.
   - **HRM ↔ SCM (Kel. 8):** HRM menyediakan master staf operasional (`SCM_OPS`); SCM mengirimkan permintaan penambahan SDM (*manpower request*) dan menyediakan rekap jam lembur operasional.
   - **HRM ↔ Keuangan (Kel. 2):** HRM mengirim permintaan pengecekan anggaran rekrutmen dan rekap tagihan *payroll*; Keuangan mengembalikan referensi persetujuan anggaran serta status pencairan (`PAID`).
3. *Bukti untuk laporan:* Diagram arsitektur integrasi dan tabel kontrak API (`docs/KONTRAK_API_HRM.md`).

## Langkah 2: Persiapan Lingkungan Pengembangan (*Environment Setup*)
1. Menggunakan bahasa pemrograman **Python 3.11**, framework web & REST API **FastAPI + Uvicorn**, library HTTP client **Requests**, serta basis data transaksional mandiri **SQLite** (menerapkan prinsip SOA *Database-per-Service*).
2. Memasang dependensi melalui `requirements.txt` (`fastapi`, `uvicorn`, `requests`, `jinja2`, `pydantic`, `pytest`).
3. *Bukti untuk laporan:* Screenshot terminal pemeriksaan versi Python, library terpasang, dan struktur folder proyek (`hrm_app/`, `mocks/`, `tests/`).

## Langkah 3: Perancangan & Pembuatan Basis Data (`hrm_app/database.py` & `seed_data.py`)
1. Merancang 13 tabel relasional SQLite dengan integritas *foreign key* (`PRAGMA foreign_keys = ON`):
   - Master & Organisasi: `company_profile`, `departments`, `employees`, `certifications`.
   - Operasional SDM: `attendance_logs`, `leave_requests`, `manpower_requests`, `applicants`.
   - Penggajian: `payroll_runs`, `payroll_items`.
   - Tata Kelola Integrasi: `integration_partners`, `api_clients`, `integration_logs`.
2. Membuat skrip *seeder* multi-tema (`THEME_PRESETS`) untuk mengisi data awal yang realistis pada kasus **Software**, **Manufaktur**, dan **Telekomunikasi** yang dapat diganti melalui UI atau API `POST /api/v1/system/switch-theme`.
3. *Bukti untuk laporan:* Skema ERD/daftar tabel serta potongan kode `SCHEMA_SQL` pada `database.py`.

## Langkah 4: Implementasi Mekanisme Autentikasi & Audit Log (`hrm_app/auth.py`)
1. Membangun mekanisme otorisasi **Bearer Token** melalui endpoint `POST /oauth/token` yang memvalidasi `client_id` dan `client_secret` pada tabel `api_clients` menggunakan `secrets.compare_digest`.
2. Membuat fungsi *dependency* `verify_bearer_token` untuk memproteksi seluruh endpoint eksternal (`/api/v1/external/...`), sehingga panggilan tanpa token atau token salah otomatis ditolak dengan HTTP **401 Unauthorized**.
3. Menambahkan fungsi `record_integration_log()` untuk merekam setiap interaksi `INBOUND` maupun `OUTBOUND` (waktu, mitra, method, URL, status code, latency ms, ringkasan payload) ke tabel `integration_logs`.
4. *Bukti untuk laporan:* Potongan kode `auth.py` serta screenshot respons `401 Unauthorized` dan `200 OK` pada Swagger UI `/docs`.

## Langkah 5: Implementasi Logika Bisnis Payroll & Adapter Integrasi (`hrm_app/services/`)
1. **Integration Adapter (`integration_service.py`):** Menerapkan *Adapter Pattern* berbasis konfigurasi tabel `integration_partners` (`base_url`, `auth_type`, `endpoints_json`, dan `field_mapping_json`) agar sistem HRM tetap kompatibel meskipun kelompok mitra mengubah URL (misal via `ngrok`) atau nama *field* JSON.
2. **Payroll Engine (`payroll_service.py`):** Menghitung gaji bersih karyawan secara otomatis berdasarkan:
   $$\text{Gaji Bersih} = (\text{Gaji Pokok} + \text{Tunjangan Tetap} + \text{Upah Lembur (Internal + SCM)} + \text{Komisi CRM}) - (\text{BPJS 3\%} + \text{PPh21} + \text{Potongan Alpha})$$
3. *Bukti untuk laporan:* Potongan kode kalkulasi payroll dan *adapter mapping*.

## Langkah 6: Pembuatan REST API Provider & Antarmuka Web HRM (`hrm_app/routers/` & `templates/`)
1. Membangun REST API Internal dan Eksternal pada `api_v1.py` (otomatis menghasilkan dokumentasi interaktif OpenAPI di `/docs`).
2. Membangun antarmuka pengguna responsif 6 halaman pada `templates/` (Dashboard Eksekutif, Karyawan & Sertifikasi, Absensi/Lembur/Cuti, Rekrutmen & Auto-Onboarding, Payroll & Slip Gaji Printable, serta Integration Hub).
3. *Bukti untuk laporan:* Screenshot kode router dan halaman Integration Hub saat mengatur endpoint mitra.

## Langkah 7: Pembuatan Simulator Kasar Kelompok Mitra & Pengujian End-to-End (`mocks/` & `tests/`)
1. Sebelum terhubung ke server asli kelompok lain, dibangun 3 *mock server* terpisah pada port berbeda (`5001` Keuangan, `5002` CRM, `5003` SCM) guna mensimulasikan komunikasi HTTP lintas aplikasi secara nyata.
2. Menjalankan pengujian otomatis menggunakan `pytest` (`tests/test_hrm_and_integration.py`) dan uji skenario lengkap lewat browser & terminal.
3. *Bukti untuk laporan:* Screenshot hasil eksekusi `pytest`, log integrasi di menu **Integration Hub**, serta tampilan slip gaji dan persetujuan pembayaran dari mock/server Keuangan.
