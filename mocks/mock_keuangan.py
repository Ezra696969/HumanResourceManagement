"""Simulator Kasar Kelompok 2: Sistem Keuangan & Akuntansi (Port 5001)."""
import html
import os
from datetime import datetime
from typing import Any

import uvicorn
from fastapi import Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from mocks.common_mock import call_hrm_endpoint, create_mock_app, get_root_prefix, render_rough_html

app, auth_dep = create_mock_app(
    service_name="Sistem Keuangan (Mock Kel. 2)",
    group_label="Kelompok 2",
    expected_client_id="hrm_kel12",
    expected_client_secret="rahasia-hrm-ke-keuangan",
)

PAYROLL_DISBURSEMENTS: dict[str, dict[str, Any]] = {}
BUDGET_REQUESTS: list[dict[str, Any]] = []
AUTO_APPROVE_BUDGET = {"enabled": True}


class PayrollDisbursementIn(BaseModel):
    batch_code: str
    period: str
    total_employees: int
    total_gross: int
    total_deductions: int
    total_net: int
    rincian_karyawan: list[dict[str, Any]] = []


class BudgetCheckIn(BaseModel):
    request_code: str
    requester_system: str = "INTERNAL"
    position_title: str
    headcount: int
    estimated_salary_per_head: int
    total_monthly_budget: int
    reason: str = ""


@app.post("/v1/payroll/disbursement")
def receive_payroll(payload: PayrollDisbursementIn, _=auth_dep):
    ref = f"FIN-PAY-{payload.period.replace('-', '')}-{len(PAYROLL_DISBURSEMENTS) + 1:02d}"
    PAYROLL_DISBURSEMENTS[payload.batch_code] = {
        "batch_code": payload.batch_code,
        "period": payload.period,
        "total_employees": payload.total_employees,
        "total_net": payload.total_net,
        "finance_ref": ref,
        "status": "PENDING_PAYMENT",
        "received_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rincian": payload.rincian_karyawan,
    }
    return {
        "finance_ref": ref,
        "status": "PENDING_PAYMENT",
        "message": f"Tagihan payroll {payload.batch_code} diterima Keuangan. Menunggu approval bayar.",
    }


@app.get("/v1/payroll/status/{batch_code}")
def get_payroll_status(batch_code: str, _=auth_dep):
    item = PAYROLL_DISBURSEMENTS.get(batch_code)
    if not item:
        return {"batch_code": batch_code, "status": "NOT_FOUND", "finance_ref": ""}
    return {
        "batch_code": batch_code,
        "status": item["status"],
        "finance_ref": item["finance_ref"],
        "note": f"Status Keuangan saat ini: {item['status']}",
    }


@app.post("/v1/anggaran/cek-rekrutmen")
def check_recruitment_budget(payload: BudgetCheckIn, _=auth_dep):
    approved = AUTO_APPROVE_BUDGET["enabled"] and payload.total_monthly_budget <= 100_000_000
    ref = f"FIN-BGT-{len(BUDGET_REQUESTS) + 1:03d}"
    BUDGET_REQUESTS.insert(
        0,
        {
            "finance_ref": ref,
            "request_code": payload.request_code,
            "position_title": payload.position_title,
            "headcount": payload.headcount,
            "total_monthly_budget": payload.total_monthly_budget,
            "approved": approved,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )
    return {
        "approved": approved,
        "finance_ref": ref,
        "message": "Anggaran disetujui Keuangan" if approved else "Anggaran melebihi pagu / ditolak Keuangan",
    }


@app.post("/ui/bayar-payroll")
def ui_pay_payroll(request: Request, batch_code: str = Form(...)):
    item = PAYROLL_DISBURSEMENTS.get(batch_code)
    if item:
        item["status"] = "PAID"
        call_hrm_endpoint(
            "POST",
            f"/api/v1/external/payroll/{batch_code}/payment-callback",
            "kel2_keuangan",
            "secret-kel2-keuangan",
            json_body={
                "status": "PAID",
                "finance_ref": item["finance_ref"],
                "note": "Dana gaji telah ditransfer oleh Keuangan (Kel. 2)",
            },
        )
    root = get_root_prefix(request)
    return RedirectResponse(f"{root}/", status_code=303)


@app.post("/ui/toggle-budget")
def ui_toggle_budget(request: Request):
    AUTO_APPROVE_BUDGET["enabled"] = not AUTO_APPROVE_BUDGET["enabled"]
    root = get_root_prefix(request)
    return RedirectResponse(f"{root}/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    root = get_root_prefix(request)
    rows_pay = "".join(
        f"""<tr>
          <td>{html.escape(v['batch_code'])}</td>
          <td>{html.escape(v['finance_ref'])}</td>
          <td>{v['total_employees']} org</td>
          <td>Rp {v['total_net']:,}</td>
          <td><b>{html.escape(v['status'])}</b></td>
          <td>
            {"<form method='post' action='" + root + "/ui/bayar-payroll'><input type='hidden' name='batch_code' value='" + html.escape(k) + "'><button type='submit'>Setujui & Bayar (LUNAS)</button></form>" if v['status'] != 'PAID' else "Sudah Dibayar"}
          </td>
        </tr>"""
        for k, v in PAYROLL_DISBURSEMENTS.items()
    ) or "<tr><td colspan='6'>Belum ada pengajuan payroll dari HRM.</td></tr>"

    rows_bgt = "".join(
        f"""<tr>
          <td>{html.escape(b['finance_ref'])}</td>
          <td>{html.escape(b['request_code'])}</td>
          <td>{html.escape(b['position_title'])} ({b['headcount']})</td>
          <td>Rp {b['total_monthly_budget']:,}</td>
          <td>{'APPROVED' if b['approved'] else 'REJECTED'}</td>
        </tr>"""
        for b in BUDGET_REQUESTS
    ) or "<tr><td colspan='5'>Belum ada cek anggaran rekrutmen.</td></tr>"

    mode_label = "AUTO-APPROVE (<= 100jt)" if AUTO_APPROVE_BUDGET["enabled"] else "AUTO-REJECT (Simulasi Tolak)"
    body = f"""
    <div class="box">
      <h3>1. Pengajuan Payroll Masuk dari HRM (Kel. 12)</h3>
      <table>
        <tr><th>Batch</th><th>Ref Keuangan</th><th>Pegawai</th><th>Total Net</th><th>Status</th><th>Aksi</th></tr>
        {rows_pay}
      </table>
    </div>
    <div class="box">
      <h3>2. Riwayat Cek Anggaran Rekrutmen</h3>
      <form method="post" action="{root}/ui/toggle-budget" style="margin-bottom:8px;">
        Mode Persetujuan: <b>{mode_label}</b>
        <button type="submit" style="margin-left:8px;">Ganti Mode</button>
      </form>
      <table>
        <tr><th>Ref</th><th>Kode MR</th><th>Posisi</th><th>Total/Bln</th><th>Hasil</th></tr>
        {rows_bgt}
      </table>
    </div>
    """
    return render_rough_html("Sistem Keuangan — Kelompok 2 (Port 5001)", "KELOMPOK 2: KEUANGAN", body)


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_KEUANGAN_PORT", "5001"))
    print(f"[Mock Keuangan Kel. 2] http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
