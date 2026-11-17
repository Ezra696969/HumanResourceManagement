"""Seluruh endpoint REST API HRM (Internal UI & External Partner Provider Kelompok 2, 7, 8)."""
import json
import sqlite3
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from hrm_app.auth import get_current_partner, issue_access_token, record_integration_log
from hrm_app.config import DEFAULT_PERIOD
from hrm_app.database import db_session
from hrm_app.schemas import (
    ApplicantCreate,
    ApplicantStageUpdate,
    AttendanceCreate,
    CertificationCreate,
    EmployeeCreate,
    EmployeeUpdate,
    InboundClientCreate,
    LeaveCreate,
    LeaveDecision,
    ManpowerRequestCreate,
    PartnerConfigUpdate,
    PaymentCallbackRequest,
    PayrollGenerateRequest,
    ThemeSwitchRequest,
    TokenRequest,
)
from hrm_app.seed_data import THEME_PRESETS, seed_database
from hrm_app.services.integration_service import (
    check_partner_health,
    fetch_scm_overtime,
    poll_payroll_status_from_finance,
    request_recruitment_budget_from_finance,
    submit_payroll_to_finance,
)
from hrm_app.services.payroll_service import (
    generate_payroll,
    get_payroll_run,
    get_payslip_item,
    list_payroll_runs,
)

router = APIRouter()


def _next_code(conn: sqlite3.Connection, table: str, col: str, prefix: str, width: int = 3) -> str:
    rows = conn.execute(f"SELECT {col} FROM {table}").fetchall()
    max_num = 0
    for r in rows:
        val = str(r[0])
        if val.startswith(prefix):
            tail = val[len(prefix):]
            if tail.isdigit():
                max_num = max(max_num, int(tail))
    return f"{prefix}{max_num + 1:0{width}d}"


# ==============================================================================
# HEALTH & OAUTH TOKEN (Terbuka untuk Mitra & Uji Konektivitas)
# ==============================================================================

@router.get("/health", tags=["System & Auth"])
def health_check() -> dict[str, Any]:
    """Memeriksa status layanan HRM Kelompok 12 dan profil perusahaan aktif."""
    with db_session() as conn:
        prof = conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone()
    return {
        "status": "OK",
        "service": "HRM System - Kelompok 12 (IAK)",
        "theme_key": prof["theme_key"] if prof else "unknown",
        "company_name": prof["company_name"] if prof else "Unconfigured",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.post("/oauth/token", tags=["System & Auth"])
def create_oauth_token(payload: TokenRequest) -> dict[str, Any]:
    """Menerbitkan Bearer access_token bagi sistem mitra (Keuangan, CRM, SCM)."""
    return issue_access_token(payload.client_id, payload.client_secret)


# ==============================================================================
# EXTERNAL PARTNER API PROVIDER (Terproteksi Bearer Token + Audit Log Inbound)
# ==============================================================================

@router.get("/api/v1/external/employees", tags=["External Integration API (Mitra)"])
def external_list_employees(
    request: Request,
    role: Optional[str] = Query(default=None, description="Filter integration_role: CRM_SALES, SCM_OPS, INTERNAL, FINANCE"),
    status_filter: Optional[str] = Query(default="AKTIF", alias="status"),
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """[Untuk CRM Kel. 7 & SCM Kel. 8] Mengambil daftar karyawan terotorisasi."""
    sql = """
        SELECT e.employee_code, e.full_name, e.email, e.phone, d.code AS department_code,
               d.name AS department_name, e.position_title, e.integration_role, e.status
        FROM employees e
        JOIN departments d ON d.id = e.department_id
        WHERE 1=1
    """
    params: list[Any] = []
    if role:
        sql += " AND e.integration_role = ?"
        params.append(role)
    if status_filter:
        sql += " AND e.status = ?"
        params.append(status_filter)
    sql += " ORDER BY e.employee_code"

    with db_session() as conn:
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]

    record_integration_log(
        "INBOUND", partner["client_id"], "GET", str(request.url.path), 200, 2,
        f"role={role}, status={status_filter}", f"Mengembalikan {len(rows)} karyawan", True,
    )
    return {"total": len(rows), "requested_by": partner["client_id"], "items": rows}


@router.get("/api/v1/external/employees/{employee_code}", tags=["External Integration API (Mitra)"])
def external_get_employee(
    employee_code: str,
    request: Request,
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """[Untuk Mitra] Mengambil profil satu karyawan berdasarkan kode_karyawan (mis. EMP-001)."""
    with db_session() as conn:
        row = conn.execute(
            """
            SELECT e.employee_code, e.full_name, e.email, e.phone, d.code AS department_code,
                   d.name AS department_name, e.position_title, e.integration_role, e.status
            FROM employees e
            JOIN departments d ON d.id = e.department_id
            WHERE e.employee_code = ?
            """,
            (employee_code,),
        ).fetchone()
    if not row:
        record_integration_log(
            "INBOUND", partner["client_id"], "GET", str(request.url.path), 404, 1,
            employee_code, "Karyawan tidak ditemukan", False,
        )
        raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")

    record_integration_log(
        "INBOUND", partner["client_id"], "GET", str(request.url.path), 200, 1,
        employee_code, f"Ditemukan: {row['full_name']}", True,
    )
    return dict(row)


@router.post("/api/v1/external/manpower-requests", status_code=201, tags=["External Integration API (Mitra)"])
def external_create_manpower_request(
    payload: ManpowerRequestCreate,
    request: Request,
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """[Untuk SCM Kel. 8 / CRM Kel. 7] Mengajukan permintaan penambahan tenaga kerja ke HRM."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        dept_id = payload.department_id
        if not dept_id:
            dept_code = payload.department_code or ("SCM" if payload.requester_system == "SCM" else "SLS")
            drow = conn.execute(
                "SELECT id FROM departments WHERE code = ? ORDER BY id LIMIT 1", (dept_code,),
            ).fetchone()
            if not drow:
                drow = conn.execute("SELECT id FROM departments ORDER BY id LIMIT 1").fetchone()
            dept_id = int(drow["id"])

        req_code = _next_code(conn, "manpower_requests", "request_code", "MR-2026-", 3)
        cur = conn.execute(
            """
            INSERT INTO manpower_requests (
                request_code, requester_system, department_id, position_title,
                headcount, estimated_salary, reason, finance_budget_status, hiring_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'BELUM_CEK', 'OPEN', ?)
            """,
            (
                req_code,
                payload.requester_system if payload.requester_system != "INTERNAL" else "SCM",
                dept_id,
                payload.position_title,
                payload.headcount,
                payload.estimated_salary,
                payload.reason,
                now,
            ),
        )
        new_id = int(cur.lastrowid)

    record_integration_log(
        "INBOUND", partner["client_id"], "POST", str(request.url.path), 201, 2,
        f"posisi={payload.position_title}, qty={payload.headcount}",
        f"Manpower request {req_code} dibuat", True,
    )
    return {
        "id": new_id,
        "request_code": req_code,
        "status": "OPEN",
        "message": "Permintaan SDM berhasil dicatat di HRM.",
    }


@router.get("/api/v1/external/manpower-requests", tags=["External Integration API (Mitra)"])
def external_list_manpower_requests(
    request: Request,
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """[Untuk Mitra] Melihat status permintaan tenaga kerja yang diajukan ke HRM."""
    with db_session() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT mr.request_code, mr.requester_system, d.name AS department_name,
                       mr.position_title, mr.headcount, mr.finance_budget_status, mr.hiring_status, mr.created_at
                FROM manpower_requests mr
                JOIN departments d ON d.id = mr.department_id
                ORDER BY mr.id DESC
                """
            ).fetchall()
        ]
    record_integration_log(
        "INBOUND", partner["client_id"], "GET", str(request.url.path), 200, 1,
        "list manpower", f"{len(rows)} permintaan", True,
    )
    return {"total": len(rows), "items": rows}


@router.post("/api/v1/external/payroll/{batch_code}/payment-callback", tags=["External Integration API (Mitra)"])
def external_payment_callback(
    batch_code: str,
    payload: PaymentCallbackRequest,
    request: Request,
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """[Untuk Keuangan Kel. 2] Callback pembaruan status pembayaran payroll dari Keuangan ke HRM."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        run = conn.execute("SELECT * FROM payroll_runs WHERE batch_code = ?", (batch_code,)).fetchone()
        if not run:
            record_integration_log(
                "INBOUND", partner["client_id"], "POST", str(request.url.path), 404, 1,
                batch_code, "Batch payroll tidak ditemukan", False,
            )
            raise HTTPException(status_code=404, detail=f"Batch {batch_code} tidak ditemukan")

        new_status = "PAID" if payload.status == "PAID" else "FINAL"
        conn.execute(
            """
            UPDATE payroll_runs
            SET status = ?, finance_batch_ref = COALESCE(NULLIF(?, ''), finance_batch_ref),
                finance_note = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_status, payload.finance_ref, payload.note or f"Callback Keuangan: {payload.status}", now, run["id"]),
        )

    record_integration_log(
        "INBOUND", partner["client_id"], "POST", str(request.url.path), 200, 2,
        f"batch={batch_code}, status={payload.status}", f"Status payroll diperbarui -> {new_status}", True,
    )
    return {"batch_code": batch_code, "status": new_status, "message": "Status pembayaran payroll diperbarui."}


@router.get("/api/v1/external/logs/summary", tags=["External Integration API (Mitra)"])
def external_logs_summary(
    request: Request,
    partner: dict[str, Any] = Depends(get_current_partner),
) -> dict[str, Any]:
    """Ringkasan jumlah panggilan API per partner (serupa endpoint log ringkasan TM12)."""
    with db_session() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                """
                SELECT direction, partner_key, method, url_or_path, COUNT(*) AS jumlah_panggilan,
                       SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS sukses
                FROM integration_logs
                GROUP BY direction, partner_key, method, url_or_path
                ORDER BY jumlah_panggilan DESC
                """
            ).fetchall()
        ]
    return {"requested_by": partner["client_id"], "summary": rows}


# ==============================================================================
# INTERNAL HRM API (Untuk Web UI & Pengelolaan Modul HRM Lengkap)
# ==============================================================================

@router.get("/api/v1/system/profile", tags=["Internal HRM - System"])
def get_system_profile() -> dict[str, Any]:
    with db_session() as conn:
        prof = dict(conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone())
    return {
        "profile": prof,
        "available_themes": {
            k: {"company_name": v["company_name"], "industry_label": v["industry_label"]}
            for k, v in THEME_PRESETS.items()
        },
    }


@router.post("/api/v1/system/switch-theme", tags=["Internal HRM - System"])
def switch_company_theme(payload: ThemeSwitchRequest) -> dict[str, Any]:
    """Mengganti profil studi kasus perusahaan (Software / Manufaktur / Telekomunikasi)."""
    res = seed_database(
        theme_key=payload.theme_key,
        force_reset=True,
        preserve_partners=payload.preserve_partners,
    )
    return {"message": f"Tema berhasil diubah ke {payload.theme_key}", **res}


@router.get("/api/v1/dashboard", tags=["Internal HRM - Dashboard"])
def get_dashboard_summary(period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    with db_session() as conn:
        prof = dict(conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone())
        emp_stats = dict(
            conn.execute(
                """
                SELECT
                    COUNT(*) AS total_all,
                    SUM(CASE WHEN status = 'AKTIF' THEN 1 ELSE 0 END) AS total_aktif,
                    SUM(CASE WHEN integration_role = 'CRM_SALES' AND status = 'AKTIF' THEN 1 ELSE 0 END) AS total_crm_sales,
                    SUM(CASE WHEN integration_role = 'SCM_OPS' AND status = 'AKTIF' THEN 1 ELSE 0 END) AS total_scm_ops
                FROM employees
                """
            ).fetchone()
        )
        pending_leaves = conn.execute(
            "SELECT COUNT(*) FROM leave_requests WHERE status = 'PENDING'"
        ).fetchone()[0]
        open_manpower = conn.execute(
            "SELECT COUNT(*) FROM manpower_requests WHERE hiring_status != 'FILLED' AND hiring_status != 'CANCELLED'"
        ).fetchone()[0]
        dept_breakdown = [
            dict(r)
            for r in conn.execute(
                """
                SELECT d.code, d.name, COUNT(e.id) AS total_employees,
                       COALESCE(SUM(e.base_salary + e.fixed_allowance), 0) AS monthly_fixed_cost
                FROM departments d
                LEFT JOIN employees e ON e.department_id = d.id AND e.status != 'NONAKTIF'
                GROUP BY d.id
                ORDER BY d.id
                """
            ).fetchall()
        ]
        payroll_row = conn.execute(
            "SELECT * FROM payroll_runs WHERE period = ? ORDER BY id DESC LIMIT 1", (period,)
        ).fetchone()
        partners = [
            dict(r)
            for r in conn.execute(
                "SELECT partner_key, partner_name, group_label, base_url, auth_type, is_active, last_health_status, last_checked_at FROM integration_partners"
            ).fetchall()
        ]
        recent_logs = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM integration_logs ORDER BY id DESC LIMIT 8"
            ).fetchall()
        ]
    return {
        "company": prof,
        "period": period,
        "kpis": {
            "total_employees": emp_stats["total_all"] or 0,
            "active_employees": emp_stats["total_aktif"] or 0,
            "crm_sales_staff": emp_stats["total_crm_sales"] or 0,
            "scm_ops_staff": emp_stats["total_scm_ops"] or 0,
            "pending_leaves": pending_leaves,
            "open_manpower_requests": open_manpower,
            "latest_payroll": dict(payroll_row) if payroll_row else None,
        },
        "department_breakdown": dept_breakdown,
        "partners": partners,
        "recent_logs": recent_logs,
    }


@router.get("/api/v1/departments", tags=["Internal HRM - Organisasi"])
def list_departments() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT d.*, COUNT(e.id) AS employee_count
            FROM departments d
            LEFT JOIN employees e ON e.department_id = d.id AND e.status != 'NONAKTIF'
            GROUP BY d.id
            ORDER BY d.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/api/v1/employees", tags=["Internal HRM - Karyawan"])
def list_employees(
    department_id: Optional[int] = None,
    integration_role: Optional[str] = None,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    search: Optional[str] = None,
) -> list[dict[str, Any]]:
    sql = """
        SELECT e.*, d.code AS department_code, d.name AS department_name
        FROM employees e
        JOIN departments d ON d.id = e.department_id
        WHERE 1=1
    """
    params: list[Any] = []
    if department_id:
        sql += " AND e.department_id = ?"
        params.append(department_id)
    if integration_role:
        sql += " AND e.integration_role = ?"
        params.append(integration_role)
    if status_filter:
        sql += " AND e.status = ?"
        params.append(status_filter)
    if search:
        sql += " AND (e.full_name LIKE ? OR e.employee_code LIKE ? OR e.position_title LIKE ?)"
        like = f"%{search}%"
        params.extend([like, like, like])
    sql += " ORDER BY e.employee_code"
    with db_session() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@router.post("/api/v1/employees", status_code=201, tags=["Internal HRM - Karyawan"])
def create_employee(payload: EmployeeCreate) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        emp_code = payload.employee_code or _next_code(conn, "employees", "employee_code", "EMP-", 3)
        try:
            cur = conn.execute(
                """
                INSERT INTO employees (
                    employee_code, full_name, email, phone, department_id, position_title,
                    employment_type, integration_role, status, join_date, base_salary,
                    fixed_allowance, overtime_rate, bank_name, bank_account, leave_quota, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    emp_code, payload.full_name, payload.email, payload.phone, payload.department_id,
                    payload.position_title, payload.employment_type, payload.integration_role, payload.status,
                    payload.join_date, payload.base_salary, payload.fixed_allowance, payload.overtime_rate,
                    payload.bank_name, payload.bank_account, payload.leave_quota, payload.notes, now,
                ),
            )
            new_id = int(cur.lastrowid)
            row = conn.execute(
                """
                SELECT e.*, d.code AS department_code, d.name AS department_name
                FROM employees e JOIN departments d ON d.id = e.department_id
                WHERE e.id = ?
                """,
                (new_id,),
            ).fetchone()
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"Kode karyawan, email, atau departemen tidak valid: {exc}")
    return dict(row)


@router.put("/api/v1/employees/{emp_id}", tags=["Internal HRM - Karyawan"])
def update_employee(emp_id: int, payload: EmployeeUpdate) -> dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Tidak ada field yang diperbarui.")
    set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
    params = list(updates.values()) + [emp_id]
    with db_session() as conn:
        try:
            cur = conn.execute(f"UPDATE employees SET {set_clause} WHERE id = ?", params)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"Gagal memperbarui data karyawan: {exc}")
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
        row = conn.execute(
            """
            SELECT e.*, d.code AS department_code, d.name AS department_name
            FROM employees e JOIN departments d ON d.id = e.department_id
            WHERE e.id = ?
            """,
            (emp_id,),
        ).fetchone()
    return dict(row)


@router.delete("/api/v1/employees/{emp_id}", tags=["Internal HRM - Karyawan"])
def deactivate_or_delete_employee(emp_id: int) -> dict[str, Any]:
    """Menonaktifkan karyawan agar riwayat payroll tetap terjaga secara referensial."""
    with db_session() as conn:
        cur = conn.execute("UPDATE employees SET status = 'NONAKTIF' WHERE id = ?", (emp_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
    return {"message": "Status karyawan diubah menjadi NONAKTIF", "id": emp_id}


@router.get("/api/v1/employees/{emp_id}/certifications", tags=["Internal HRM - Karyawan"])
def list_employee_certifications(emp_id: int) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM certifications WHERE employee_id = ? ORDER BY id DESC", (emp_id,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v1/certifications", status_code=201, tags=["Internal HRM - Karyawan"])
def add_certification(payload: CertificationCreate) -> dict[str, Any]:
    with db_session() as conn:
        try:
            cur = conn.execute(
                """
                INSERT INTO certifications (employee_id, cert_name, issuer, issued_date, expiry_date, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (payload.employee_id, payload.cert_name, payload.issuer, payload.issued_date, payload.expiry_date, payload.status),
            )
            row = conn.execute("SELECT * FROM certifications WHERE id = ?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="employee_id tidak valid")
    return dict(row)


@router.delete("/api/v1/certifications/{cert_id}", tags=["Internal HRM - Karyawan"])
def delete_certification(cert_id: int) -> dict[str, Any]:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM certifications WHERE id = ?", (cert_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Sertifikasi tidak ditemukan")
    return {"deleted": cert_id}


# ==============================================================================
# ABSENSI, LEMBUR & CUTI
# ==============================================================================

@router.get("/api/v1/attendance", tags=["Internal HRM - Absensi & Cuti"])
def list_attendance(period: Optional[str] = None) -> list[dict[str, Any]]:
    sql = """
        SELECT a.*, e.employee_code, e.full_name, d.name AS department_name
        FROM attendance_logs a
        JOIN employees e ON e.id = a.employee_id
        JOIN departments d ON d.id = e.department_id
        WHERE 1=1
    """
    params: list[Any] = []
    if period:
        sql += " AND a.work_date LIKE ?"
        params.append(f"{period}-%")
    sql += " ORDER BY a.work_date DESC, e.employee_code"
    with db_session() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


@router.post("/api/v1/attendance", status_code=201, tags=["Internal HRM - Absensi & Cuti"])
def upsert_attendance(payload: AttendanceCreate) -> dict[str, Any]:
    with db_session() as conn:
        try:
            conn.execute(
                """
                INSERT INTO attendance_logs (employee_id, work_date, status, regular_hours, overtime_hours, source, note)
                VALUES (?, ?, ?, ?, ?, 'INTERNAL', ?)
                ON CONFLICT(employee_id, work_date, source)
                DO UPDATE SET status = excluded.status,
                              regular_hours = excluded.regular_hours,
                              overtime_hours = excluded.overtime_hours,
                              note = excluded.note
                """,
                (payload.employee_id, payload.work_date, payload.status, payload.regular_hours, payload.overtime_hours, payload.note),
            )
            row = conn.execute(
                """
                SELECT a.*, e.employee_code, e.full_name
                FROM attendance_logs a JOIN employees e ON e.id = a.employee_id
                WHERE a.employee_id = ? AND a.work_date = ? AND a.source = 'INTERNAL'
                """,
                (payload.employee_id, payload.work_date),
            ).fetchone()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=400, detail="employee_id tidak valid")
    return dict(row)


@router.post("/api/v1/attendance/sync-scm", tags=["Internal HRM - Absensi & Cuti"])
def sync_overtime_from_scm(period: str = DEFAULT_PERIOD) -> dict[str, Any]:
    """Menarik catatan jam lembur operasional dari server SCM (Kelompok 8)."""
    res = fetch_scm_overtime(period)
    if not res["success"]:
        raise HTTPException(status_code=502, detail=res)
    return res


@router.get("/api/v1/leaves", tags=["Internal HRM - Absensi & Cuti"])
def list_leaves() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT l.*, e.employee_code, e.full_name, e.leave_quota, d.name AS department_name
            FROM leave_requests l
            JOIN employees e ON e.id = l.employee_id
            JOIN departments d ON d.id = e.department_id
            ORDER BY CASE l.status WHEN 'PENDING' THEN 0 ELSE 1 END, l.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v1/leaves", status_code=201, tags=["Internal HRM - Absensi & Cuti"])
def create_leave_request(payload: LeaveCreate) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        emp = conn.execute("SELECT leave_quota FROM employees WHERE id = ?", (payload.employee_id,)).fetchone()
        if not emp:
            raise HTTPException(status_code=404, detail="Karyawan tidak ditemukan")
        if payload.leave_type == "TAHUNAN" and payload.days_count > emp["leave_quota"]:
            raise HTTPException(status_code=400, detail=f"Sisa kuota cuti ({emp['leave_quota']} hari) tidak mencukupi.")
        cur = conn.execute(
            """
            INSERT INTO leave_requests (employee_id, leave_type, start_date, end_date, days_count, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
            """,
            (payload.employee_id, payload.leave_type, payload.start_date, payload.end_date, payload.days_count, payload.reason, now),
        )
        row = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.patch("/api/v1/leaves/{leave_id}", tags=["Internal HRM - Absensi & Cuti"])
def decide_leave_request(leave_id: int, payload: LeaveDecision) -> dict[str, Any]:
    with db_session() as conn:
        leave = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
        if not leave:
            raise HTTPException(status_code=404, detail="Pengajuan cuti tidak ditemukan")
        if leave["status"] != "PENDING":
            raise HTTPException(status_code=400, detail=f"Pengajuan sudah diputuskan ({leave['status']}).")

        if payload.status == "APPROVED" and leave["leave_type"] == "TAHUNAN":
            conn.execute(
                "UPDATE employees SET leave_quota = MAX(0, leave_quota - ?) WHERE id = ?",
                (leave["days_count"], leave["employee_id"]),
            )
        conn.execute(
            "UPDATE leave_requests SET status = ?, reviewed_by = ? WHERE id = ?",
            (payload.status, payload.reviewed_by, leave_id),
        )
        updated = conn.execute("SELECT * FROM leave_requests WHERE id = ?", (leave_id,)).fetchone()
    return dict(updated)


# ==============================================================================
# REKRUTMEN & MANPOWER REQUEST (Terintegrasi dengan SCM & Keuangan)
# ==============================================================================

@router.get("/api/v1/manpower-requests", tags=["Internal HRM - Rekrutmen"])
def list_manpower_requests() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT mr.*, d.code AS department_code, d.name AS department_name,
                   (SELECT COUNT(*) FROM applicants a WHERE a.manpower_request_id = mr.id) AS applicant_count,
                   (SELECT COUNT(*) FROM applicants a WHERE a.manpower_request_id = mr.id AND a.stage = 'HIRED') AS hired_count
            FROM manpower_requests mr
            JOIN departments d ON d.id = mr.department_id
            ORDER BY mr.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v1/manpower-requests", status_code=201, tags=["Internal HRM - Rekrutmen"])
def create_manpower_request(payload: ManpowerRequestCreate) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        dept_id = payload.department_id
        if not dept_id:
            drow = conn.execute("SELECT id FROM departments ORDER BY id LIMIT 1").fetchone()
            dept_id = int(drow["id"])
        req_code = _next_code(conn, "manpower_requests", "request_code", "MR-2026-", 3)
        cur = conn.execute(
            """
            INSERT INTO manpower_requests (
                request_code, requester_system, department_id, position_title,
                headcount, estimated_salary, reason, finance_budget_status, hiring_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'BELUM_CEK', 'OPEN', ?)
            """,
            (req_code, payload.requester_system, dept_id, payload.position_title, payload.headcount, payload.estimated_salary, payload.reason, now),
        )
        row = conn.execute("SELECT * FROM manpower_requests WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.post("/api/v1/manpower-requests/{req_id}/check-budget", tags=["Internal HRM - Rekrutmen"])
def check_manpower_budget(req_id: int) -> dict[str, Any]:
    """Mengirim permintaan approval anggaran rekrutmen ke Sistem Keuangan (Kelompok 2)."""
    with db_session() as conn:
        row = conn.execute("SELECT * FROM manpower_requests WHERE id = ?", (req_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Manpower request tidak ditemukan")
    res = request_recruitment_budget_from_finance(dict(row))
    if not res["success"]:
        raise HTTPException(status_code=502, detail=res)
    return res


@router.get("/api/v1/applicants", tags=["Internal HRM - Rekrutmen"])
def list_applicants() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT a.*, mr.request_code, mr.position_title, mr.department_id, mr.estimated_salary,
                   mr.requester_system, d.name AS department_name
            FROM applicants a
            JOIN manpower_requests mr ON mr.id = a.manpower_request_id
            JOIN departments d ON d.id = mr.department_id
            ORDER BY a.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v1/applicants", status_code=201, tags=["Internal HRM - Rekrutmen"])
def create_applicant(payload: ApplicantCreate) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        mr = conn.execute("SELECT id FROM manpower_requests WHERE id = ?", (payload.manpower_request_id,)).fetchone()
        if not mr:
            raise HTTPException(status_code=404, detail="Lowongan manpower request tidak ditemukan")
        cur = conn.execute(
            """
            INSERT INTO applicants (manpower_request_id, full_name, email, phone, skills, stage, created_at)
            VALUES (?, ?, ?, ?, ?, 'APPLIED', ?)
            """,
            (payload.manpower_request_id, payload.full_name, payload.email, payload.phone, payload.skills, now),
        )
        row = conn.execute("SELECT * FROM applicants WHERE id = ?", (cur.lastrowid,)).fetchone()
    return dict(row)


@router.patch("/api/v1/applicants/{app_id}/stage", tags=["Internal HRM - Rekrutmen"])
def update_applicant_stage(app_id: int, payload: ApplicantStageUpdate) -> dict[str, Any]:
    """Memperbarui tahap pelamar; jika HIRED otomatis onboarding menjadi karyawan baru."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")
    with db_session() as conn:
        app_row = conn.execute(
            """
            SELECT a.*, mr.department_id, mr.position_title, mr.estimated_salary, mr.headcount, mr.requester_system
            FROM applicants a
            JOIN manpower_requests mr ON mr.id = a.manpower_request_id
            WHERE a.id = ?
            """,
            (app_id,),
        ).fetchone()
        if not app_row:
            raise HTTPException(status_code=404, detail="Pelamar tidak ditemukan")

        hired_code = app_row["hired_employee_code"]
        if payload.stage == "HIRED" and app_row["stage"] != "HIRED":
            emp_code = _next_code(conn, "employees", "employee_code", "EMP-", 3)
            role = payload.hire_integration_role
            if role == "INTERNAL":
                if app_row["requester_system"] == "SCM":
                    role = "SCM_OPS"
                elif app_row["requester_system"] == "CRM":
                    role = "CRM_SALES"
            try:
                conn.execute(
                    """
                    INSERT INTO employees (
                        employee_code, full_name, email, phone, department_id, position_title,
                        employment_type, integration_role, status, join_date, base_salary,
                        fixed_allowance, overtime_rate, bank_name, bank_account, leave_quota, notes, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'KONTRAK', ?, 'AKTIF', ?, ?, 1000000, 55000, ?, ?, 12, ?, ?)
                    """,
                    (
                        emp_code, app_row["full_name"], app_row["email"], app_row["phone"],
                        app_row["department_id"], app_row["position_title"], role, today,
                        app_row["estimated_salary"], payload.hire_bank_name, payload.hire_bank_account,
                        f"Rekrutmen dari {app_row['requester_system']}", now,
                    ),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(status_code=409, detail=f"Email '{app_row['email']}' sudah terdaftar sebagai karyawan.")

            hired_code = emp_code
            hired_total = conn.execute(
                "SELECT COUNT(*) FROM applicants WHERE manpower_request_id = ? AND stage = 'HIRED'",
                (app_row["manpower_request_id"],),
            ).fetchone()[0] + 1
            new_mr_status = "FILLED" if hired_total >= app_row["headcount"] else "INTERVIEW"
            conn.execute(
                "UPDATE manpower_requests SET hiring_status = ? WHERE id = ?",
                (new_mr_status, app_row["manpower_request_id"]),
            )

        conn.execute(
            "UPDATE applicants SET stage = ?, hired_employee_code = ? WHERE id = ?",
            (payload.stage, hired_code, app_id),
        )
        updated = conn.execute("SELECT * FROM applicants WHERE id = ?", (app_id,)).fetchone()
    return dict(updated)


# ==============================================================================
# PENGGAJIAN (PAYROLL ENGINE & INTEGRASI KEUANGAN / CRM / SCM)
# ==============================================================================

@router.get("/api/v1/payroll", tags=["Internal HRM - Payroll"])
def get_all_payroll_runs() -> list[dict[str, Any]]:
    return list_payroll_runs()


@router.get("/api/v1/payroll/payslip/{item_id}", tags=["Internal HRM - Payroll"])
def get_payslip(item_id: int) -> dict[str, Any]:
    item = get_payslip_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Slip gaji tidak ditemukan")
    return item


@router.get("/api/v1/payroll/{period}", tags=["Internal HRM - Payroll"])
def get_payroll_by_period(period: str) -> dict[str, Any]:
    run = get_payroll_run(period)
    if not run:
        return {"period": period, "exists": False, "items": []}
    return {"exists": True, **run}


@router.post("/api/v1/payroll/generate", tags=["Internal HRM - Payroll"])
def api_generate_payroll(payload: PayrollGenerateRequest) -> dict[str, Any]:
    try:
        return generate_payroll(payload.period, sync_external=payload.sync_external)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/api/v1/payroll/{period}/submit-finance", tags=["Internal HRM - Payroll"])
def api_submit_payroll_to_finance(period: str) -> dict[str, Any]:
    run = get_payroll_run(period)
    if not run:
        raise HTTPException(status_code=404, detail=f"Payroll periode {period} belum di-generate.")
    res = submit_payroll_to_finance(run, run["items"])
    if not res["success"]:
        raise HTTPException(status_code=502, detail=res)
    return res


@router.post("/api/v1/payroll/{period}/sync-finance-status", tags=["Internal HRM - Payroll"])
def api_sync_payroll_finance_status(period: str) -> dict[str, Any]:
    run = get_payroll_run(period)
    if not run:
        raise HTTPException(status_code=404, detail=f"Payroll periode {period} tidak ditemukan.")
    res = poll_payroll_status_from_finance(run["batch_code"])
    if not res["success"]:
        raise HTTPException(status_code=502, detail=res)
    return res


# ==============================================================================
# INTEGRATION HUB (Konfigurasi Adaptif Partner, Kredensial Inbound, & Logs)
# ==============================================================================

@router.get("/api/v1/integration/partners", tags=["Internal HRM - Integration Hub"])
def list_partners() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM integration_partners ORDER BY group_label").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["endpoints"] = json.loads(d["endpoints_json"])
        d["field_mapping"] = json.loads(d["field_mapping_json"])
        result.append(d)
    return result


@router.put("/api/v1/integration/partners/{partner_key}", tags=["Internal HRM - Integration Hub"])
def update_partner(partner_key: str, payload: PartnerConfigUpdate) -> dict[str, Any]:
    with db_session() as conn:
        existing = conn.execute(
            "SELECT * FROM integration_partners WHERE partner_key = ?", (partner_key,)
        ).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Partner tidak ditemukan")

        conn.execute(
            """
            UPDATE integration_partners
            SET partner_name = COALESCE(?, partner_name),
                base_url = ?, auth_type = ?, token_endpoint = ?,
                client_id = ?, client_secret = ?, api_key_header = ?, api_key_value = ?,
                endpoints_json = ?, field_mapping_json = ?, is_active = ?
            WHERE partner_key = ?
            """,
            (
                payload.partner_name,
                payload.base_url.rstrip("/"),
                payload.auth_type,
                payload.token_endpoint,
                payload.client_id,
                payload.client_secret,
                payload.api_key_header,
                payload.api_key_value,
                json.dumps(payload.endpoints),
                json.dumps(payload.field_mapping),
                1 if payload.is_active else 0,
                partner_key,
            ),
        )
        updated = dict(conn.execute("SELECT * FROM integration_partners WHERE partner_key = ?", (partner_key,)).fetchone())
    updated["endpoints"] = json.loads(updated["endpoints_json"])
    updated["field_mapping"] = json.loads(updated["field_mapping_json"])
    return updated


@router.post("/api/v1/integration/partners/{partner_key}/health", tags=["Internal HRM - Integration Hub"])
def check_single_partner_health(partner_key: str) -> dict[str, Any]:
    try:
        return check_partner_health(partner_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/v1/integration/partners/health-all", tags=["Internal HRM - Integration Hub"])
def check_all_partners_health() -> list[dict[str, Any]]:
    return [check_partner_health(k) for k in ("keuangan", "crm", "scm")]


@router.get("/api/v1/integration/clients", tags=["Internal HRM - Integration Hub"])
def list_inbound_clients() -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT client_id, client_secret, partner_name, allowed_scopes, is_active, created_at FROM api_clients ORDER BY client_id"
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/v1/integration/clients", status_code=201, tags=["Internal HRM - Integration Hub"])
def create_inbound_client(payload: InboundClientCreate) -> dict[str, Any]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        try:
            conn.execute(
                """
                INSERT INTO api_clients (client_id, client_secret, partner_name, allowed_scopes, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """,
                (payload.client_id, payload.client_secret, payload.partner_name, payload.allowed_scopes, now),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="client_id sudah terdaftar")
    return {"client_id": payload.client_id, "partner_name": payload.partner_name, "is_active": 1}


@router.delete("/api/v1/integration/clients/{client_id}", tags=["Internal HRM - Integration Hub"])
def delete_inbound_client(client_id: str) -> dict[str, Any]:
    with db_session() as conn:
        cur = conn.execute("DELETE FROM api_clients WHERE client_id = ?", (client_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Client tidak ditemukan")
    return {"deleted": client_id}


@router.get("/api/v1/integration/logs", tags=["Internal HRM - Integration Hub"])
def list_integration_logs(limit: int = Query(default=50, ge=1, le=200)) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT * FROM integration_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/api/v1/integration/logs", tags=["Internal HRM - Integration Hub"])
def clear_integration_logs() -> dict[str, Any]:
    with db_session() as conn:
        conn.execute("DELETE FROM integration_logs")
    return {"message": "Log integrasi dibersihkan"}
