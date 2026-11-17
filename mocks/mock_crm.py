"""Simulator Kasar Kelompok 7: Sistem CRM & Komisi Sales (Port 5002)."""
import html
import os
from typing import Any

import uvicorn
from fastapi import Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mocks.common_mock import call_hrm_endpoint, create_mock_app, get_root_prefix, render_rough_html

app, auth_dep = create_mock_app(
    service_name="Sistem CRM (Mock Kel. 7)",
    group_label="Kelompok 7",
    expected_client_id="hrm_kel12",
    expected_client_secret="rahasia-hrm-ke-crm",
)

# Data kasar komisi sales per periode (EMP-005 & EMP-006 adalah CRM_SALES pada tema Manufaktur)
SALES_COMMISSIONS: list[dict[str, Any]] = [
    {"periode": "2026-11", "kode_karyawan": "EMP-005", "nama": "Industrial B2B Sales Lead", "jumlah_deal": 4, "total_komisi": 3200000},
    {"periode": "2026-11", "kode_karyawan": "EMP-006", "nama": "Regional Account Executive", "jumlah_deal": 2, "total_komisi": 1750000},
]
LAST_HRM_SYNC: dict[str, Any] = {"ok": None, "items": [], "message": "Belum tarik data dari HRM"}


@app.get("/v1/sales/komisi")
def get_commissions(periode: str = Query(default="2026-11"), _=auth_dep):
    filtered = [x for x in SALES_COMMISSIONS if x["periode"] == periode]
    return {"periode": periode, "items": filtered}


@app.post("/ui/tambah-komisi")
def ui_add_commission(
    request: Request,
    periode: str = Form("2026-11"),
    kode_karyawan: str = Form(...),
    jumlah_deal: int = Form(1),
    total_komisi: int = Form(1000000),
):
    root = get_root_prefix(request)
    code = kode_karyawan.strip().upper()
    for row in SALES_COMMISSIONS:
        if row["periode"] == periode and row["kode_karyawan"] == code:
            row["jumlah_deal"] += jumlah_deal
            row["total_komisi"] += total_komisi
            return RedirectResponse(f"{root}/", status_code=303)
    SALES_COMMISSIONS.append(
        {"periode": periode, "kode_karyawan": code, "nama": "Input Manual CRM", "jumlah_deal": jumlah_deal, "total_komisi": total_komisi}
    )
    return RedirectResponse(f"{root}/", status_code=303)


@app.post("/ui/tarik-sales-hrm")
def ui_sync_sales(request: Request):
    ok, data = call_hrm_endpoint("GET", "/api/v1/external/employees?role=CRM_SALES", "kel7_crm", "secret-kel7-crm")
    if ok and isinstance(data, dict):
        LAST_HRM_SYNC["ok"] = True
        LAST_HRM_SYNC["items"] = data.get("items", [])
        LAST_HRM_SYNC["message"] = f"Berhasil tarik {len(LAST_HRM_SYNC['items'])} staf sales dari HRM!"
    else:
        LAST_HRM_SYNC["ok"] = False
        LAST_HRM_SYNC["message"] = str(data)
    root = get_root_prefix(request)
    return RedirectResponse(f"{root}/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    root = get_root_prefix(request)
    rows = "".join(
        f"<tr><td>{html.escape(r['periode'])}</td><td><b>{html.escape(r['kode_karyawan'])}</b></td><td>{r['jumlah_deal']}</td><td>Rp {r['total_komisi']:,}</td></tr>"
        for r in SALES_COMMISSIONS
    )
    hrm_rows = "".join(
        f"<li><b>{html.escape(e['employee_code'])}</b> — {html.escape(e['full_name'])} ({html.escape(e['position_title'])})</li>"
        for e in LAST_HRM_SYNC["items"]
    )
    body = f"""
    <div class="box">
      <h3>1. Rekap Komisi Sales (Akan Ditarik oleh Payroll HRM)</h3>
      <table>
        <tr><th>Periode</th><th>Kode Karyawan</th><th>Jumlah Deal</th><th>Total Komisi</th></tr>
        {rows}
      </table>
      <form method="post" action="{root}/ui/tambah-komisi" style="margin-top:12px;">
        <b>Tambah Deal/Komisi:</b>
        Periode <input name="periode" value="2026-11" size="8">
        Kode <input name="kode_karyawan" value="EMP-005" size="9">
        Deal <input name="jumlah_deal" type="number" value="1" style="width:55px;">
        Komisi (Rp) <input name="total_komisi" type="number" value="1500000" style="width:110px;">
        <button type="submit">Simpan Deal</button>
      </form>
    </div>
    <div class="box">
      <h3>2. Tarik Daftar Staf Sales dari HRM (Kel. 12)</h3>
      <form method="post" action="{root}/ui/tarik-sales-hrm">
        <button type="submit">Tarik Sales dari API HRM</button>
      </form>
      <p style="font-size:13px;">Status: <b>{html.escape(LAST_HRM_SYNC['message'])}</b></p>
      <ul>{hrm_rows}</ul>
    </div>
    """
    return render_rough_html("Sistem CRM — Kelompok 7 (Port 5002)", "KELOMPOK 7: CRM", body)


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_CRM_PORT", "5002"))
    print(f"[Mock CRM Kel. 7] http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
