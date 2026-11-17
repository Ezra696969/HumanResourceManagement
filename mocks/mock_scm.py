"""Simulator Kasar Kelompok 8: Sistem SCM (Supply Chain / Operasional) (Port 5003)."""
import html
import os
from typing import Any

import uvicorn
from fastapi import Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from mocks.common_mock import call_hrm_endpoint, create_mock_app, get_root_prefix, render_rough_html

app, auth_dep = create_mock_app(
    service_name="Sistem SCM (Mock Kel. 8)",
    group_label="Kelompok 8",
    expected_client_id="hrm_kel12",
    expected_client_secret="rahasia-hrm-ke-scm",
)

# EMP-003 & EMP-004 adalah SCM_OPS PT Panata Jaya Mandiri (Operator Stamping/CNC & Kepala Gudang)
SCM_OVERTIME: list[dict[str, Any]] = [
    {"periode": "2026-11", "kode_karyawan": "EMP-003", "total_jam_lembur": 6.0, "catatan": "Lembur shift produksi komponen otomotif"},
    {"periode": "2026-11", "kode_karyawan": "EMP-004", "total_jam_lembur": 4.0, "catatan": "Stock opname & Goods Receipt bahan baku PO/GR"},
]
LAST_SCM_MSG: dict[str, Any] = {"staff": [], "status_msg": "Belum ada panggilan ke HRM"}


@app.get("/v1/operasional/lembur")
def get_overtime(periode: str = Query(default="2026-11"), _=auth_dep):
    filtered = [x for x in SCM_OVERTIME if x["periode"] == periode]
    return {"periode": periode, "items": filtered}


@app.post("/ui/tambah-lembur")
def ui_add_overtime(
    request: Request,
    periode: str = Form("2026-11"),
    kode_karyawan: str = Form("EMP-003"),
    total_jam_lembur: float = Form(2.0),
    catatan: str = Form("Lembur bongkar muat / site"),
):
    root = get_root_prefix(request)
    code = kode_karyawan.strip().upper()
    for row in SCM_OVERTIME:
        if row["periode"] == periode and row["kode_karyawan"] == code:
            row["total_jam_lembur"] += total_jam_lembur
            row["catatan"] = catatan
            return RedirectResponse(f"{root}/", status_code=303)
    SCM_OVERTIME.append(
        {"periode": periode, "kode_karyawan": code, "total_jam_lembur": total_jam_lembur, "catatan": catatan}
    )
    return RedirectResponse(f"{root}/", status_code=303)


@app.post("/ui/tarik-ops-hrm")
def ui_sync_ops(request: Request):
    ok, data = call_hrm_endpoint("GET", "/api/v1/external/employees?role=SCM_OPS", "kel8_scm", "secret-kel8-scm")
    if ok and isinstance(data, dict):
        LAST_SCM_MSG["staff"] = data.get("items", [])
        LAST_SCM_MSG["status_msg"] = f"Berhasil tarik {len(LAST_SCM_MSG['staff'])} staf SCM dari HRM!"
    else:
        LAST_SCM_MSG["status_msg"] = str(data)
    root = get_root_prefix(request)
    return RedirectResponse(f"{root}/", status_code=303)


@app.post("/ui/minta-sdm-hrm")
def ui_request_manpower(
    request: Request,
    position_title: str = Form("Staff Logistik & Gudang Tambahan"),
    headcount: int = Form(1),
    estimated_salary: int = Form(7000000),
    reason: str = Form("Volume distribusi SCM meningkat 30%"),
):
    ok, data = call_hrm_endpoint(
        "POST",
        "/api/v1/external/manpower-requests",
        "kel8_scm",
        "secret-kel8-scm",
        json_body={
            "requester_system": "SCM",
            "position_title": position_title,
            "headcount": headcount,
            "estimated_salary": estimated_salary,
            "reason": reason,
        },
    )
    LAST_SCM_MSG["status_msg"] = f"Manpower Request ke HRM -> {'SUKSES' if ok else 'GAGAL'}: {data}"
    root = get_root_prefix(request)
    return RedirectResponse(f"{root}/", status_code=303)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    root = get_root_prefix(request)
    rows = "".join(
        f"<tr><td>{html.escape(r['periode'])}</td><td><b>{html.escape(r['kode_karyawan'])}</b></td><td>{r['total_jam_lembur']} jam</td><td>{html.escape(r['catatan'])}</td></tr>"
        for r in SCM_OVERTIME
    )
    staff_items = "".join(
        f"<li><b>{html.escape(e['employee_code'])}</b> — {html.escape(e['full_name'])} ({html.escape(e['position_title'])})</li>"
        for e in LAST_SCM_MSG["staff"]
    )
    body = f"""
    <div class="box">
      <h3>1. Rekap Jam Lembur Operasional SCM (Akan Ditarik HRM)</h3>
      <table>
        <tr><th>Periode</th><th>Kode Karyawan</th><th>Jam Lembur</th><th>Catatan</th></tr>
        {rows}
      </table>
      <form method="post" action="{root}/ui/tambah-lembur" style="margin-top:12px;">
        <b>Tambah Lembur:</b>
        Periode <input name="periode" value="2026-11" size="8">
        Kode <input name="kode_karyawan" value="EMP-003" size="9">
        Jam <input name="total_jam_lembur" type="number" step="0.5" value="3" style="width:60px;">
        Catatan <input name="catatan" value="Lembur operasional tambahan" size="25">
        <button type="submit">Simpan Lembur</button>
      </form>
    </div>
    <div class="box">
      <h3>2. Kirim Permintaan Tenaga Kerja (Manpower Request) ke HRM (Kel. 12)</h3>
      <form method="post" action="{root}/ui/minta-sdm-hrm">
        Posisi: <input name="position_title" value="Koordinator Gudang Shift 2" size="26">
        Jml: <input name="headcount" type="number" value="1" style="width:50px;">
        Est. Gaji: <input name="estimated_salary" type="number" value="7500000" style="width:100px;">
        Alasan: <input name="reason" value="Peningkatan order pengiriman" size="26">
        <button type="submit">Kirim ke HRM</button>
      </form>
    </div>
    <div class="box">
      <h3>3. Tarik Daftar Staf SCM dari API HRM</h3>
      <form method="post" action="{root}/ui/tarik-ops-hrm">
        <button type="submit">Tarik Staf SCM_OPS dari HRM</button>
      </form>
      <p style="font-size:13px;">Status: <b>{html.escape(LAST_SCM_MSG['status_msg'])}</b></p>
      <ul>{staff_items}</ul>
    </div>
    """
    return render_rough_html("Sistem SCM — Kelompok 8 (Port 5003)", "KELOMPOK 8: SCM", body)


if __name__ == "__main__":
    port = int(os.environ.get("MOCK_SCM_PORT", "5003"))
    print(f"[Mock SCM Kel. 8] http://127.0.0.1:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
