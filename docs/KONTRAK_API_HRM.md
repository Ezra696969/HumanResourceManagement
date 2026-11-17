# Kontrak API Resmi Sistem HRM — Kelompok 12 (IAK)

Dokumen ini disiapkan untuk dibagikan kepada **Kelompok 2 (Keuangan)**, **Kelompok 7 (CRM)**, dan **Kelompok 8 (SCM)** saat diskusi penyamaan format data dan alamat server (`ngrok` atau hosting).

---

## 1. Autentikasi API Inbound (Mitra Memanggil HRM)

Seluruh endpoint eksternal HRM (`/api/v1/external/...`) diamankan menggunakan **Bearer Token** (serupa pola TM12).

1. **Minta Token:** `POST /oauth/token`
   ```json
   {
     "client_id": "kel7_crm",
     "client_secret": "secret-kel7-crm"
   }
   ```
   **Kredensial Default Terdaftar:**
   - **Kelompok 2 (Keuangan):** `client_id = "kel2_keuangan"`, `client_secret = "secret-kel2-keuangan"`
   - **Kelompok 7 (CRM):** `client_id = "kel7_crm"`, `client_secret = "secret-kel7-crm"`
   - **Kelompok 8 (SCM):** `client_id = "kel8_scm"`, `client_secret = "secret-kel8-scm"`
   *(Dapat ditambah/ubah langsung melalui menu **Integration Hub** di UI HRM).*

2. **Gunakan Token pada Header:**
   ```http
   Authorization: Bearer <access_token>
   ngrok-skip-browser-warning: true
   ```

---

## 2. Daftar Endpoint HRM yang Disediakan untuk Kelompok Lain (Inbound)

| Sistem Pemanggil | Method & Endpoint | Fungsi |
| :--- | :--- | :--- |
| **CRM (Kel. 7)** | `GET /api/v1/external/employees?role=CRM_SALES&status=AKTIF` | Mengambil daftar staf Sales yang aktif beserta `employee_code` (`EMP-xxx`). |
| **SCM (Kel. 8)** | `GET /api/v1/external/employees?role=SCM_OPS&status=AKTIF` | Mengambil daftar staf gudang/teknisi lapangan yang aktif. |
| **Semua Mitra** | `GET /api/v1/external/employees/{employee_code}` | Mengecek profil & keaktifan 1 karyawan berdasarkan kode unik (`EMP-001`). |
| **SCM / CRM** | `POST /api/v1/external/manpower-requests` | Mengirim permintaan penambahan tenaga kerja baru ke modul Rekrutmen HRM. |
| **Keuangan (Kel. 2)** | `POST /api/v1/external/payroll/{batch_code}/payment-callback` | Mengirim notifikasi/update status bahwa batch gaji sudah dibayar (`PAID`). |

### Contoh Payload `POST /api/v1/external/manpower-requests` (dari SCM/CRM)
```json
{
  "requester_system": "SCM",
  "position_title": "Operator Gudang Shift 2",
  "headcount": 2,
  "estimated_salary": 7000000,
  "reason": "Kenaikan volume distribusi kuartal IV"
}
```

### Contoh Payload `POST /api/v1/external/payroll/PAY-2026-11/payment-callback` (dari Keuangan)
```json
{
  "status": "PAID",
  "finance_ref": "FIN-PAY-202611-01",
  "note": "Transfer gaji batch November selesai diproses"
}
```

---

## 3. Endpoint Mitra yang Dipanggil oleh HRM (Outbound)

Jika Kelompok 2, 7, dan 8 memiliki nama endpoint atau nama *field JSON* berbeda saat mereka membangun sistemnya nanti, **tidak perlu mengubah kode HRM** — cukup sesuaikan melalui menu **Integration Hub → Edit Adapter** pada Web UI HRM.

### A. Keuangan (Kelompok 2)
- `POST /v1/payroll/disbursement` → HRM mengirim total gaji bersih, pajak PPh21, dan rincian rekening karyawan.
- `GET /v1/payroll/status/{batch_code}` → HRM mengecek status pencairan gaji (`PENDING_PAYMENT` / `PAID`).
- `POST /v1/anggaran/cek-rekrutmen` → HRM mengecek persetujuan anggaran saat ada permintaan rekrutmen baru.

### B. CRM (Kelompok 7)
- `GET /v1/sales/komisi?periode=2026-11` → HRM menarik daftar komisi per `kode_karyawan` untuk dihitung otomatis di Payroll.

### C. SCM (Kelompok 8)
- `GET /v1/operasional/lembur?periode=2026-11` → HRM menarik daftar `total_jam_lembur` per `kode_karyawan` untuk dihitung ke absensi dan lembur Payroll.
