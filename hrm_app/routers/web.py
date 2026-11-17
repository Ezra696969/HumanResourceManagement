"""Router halaman Web UI untuk Sistem HRM Kelompok 12."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from hrm_app.config import DEFAULT_PERIOD
from hrm_app.database import db_session

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

web_router = APIRouter(include_in_schema=False)


def _base_context(request: Request, active_page: str, page_title: str) -> dict:
    with db_session() as conn:
        prof = conn.execute("SELECT * FROM company_profile WHERE id = 1").fetchone()
    return {
        "request": request,
        "active_page": active_page,
        "page_title": page_title,
        "company": dict(prof) if prof else {
            "theme_key": "manufaktur",
            "company_name": "PT ABC",
            "industry_label": "Industri Manufaktur & Perakitan Komponen",
        },
        "default_period": DEFAULT_PERIOD,
    }


@web_router.get("/", response_class=HTMLResponse)
def page_dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", _base_context(request, "dashboard", "Dashboard Eksekutif HRM"))


@web_router.get("/employees", response_class=HTMLResponse)
def page_employees(request: Request):
    return templates.TemplateResponse(request, "employees.html", _base_context(request, "employees", "Karyawan & Organisasi"))


@web_router.get("/attendance", response_class=HTMLResponse)
def page_attendance(request: Request):
    return templates.TemplateResponse(request, "attendance.html", _base_context(request, "attendance", "Absensi, Lembur & Cuti"))


@web_router.get("/recruitment", response_class=HTMLResponse)
def page_recruitment(request: Request):
    return templates.TemplateResponse(request, "recruitment.html", _base_context(request, "recruitment", "Rekrutmen & Manpower"))


@web_router.get("/payroll", response_class=HTMLResponse)
def page_payroll(request: Request):
    return templates.TemplateResponse(request, "payroll.html", _base_context(request, "payroll", "Penggajian (Payroll) Terintegrasi"))


@web_router.get("/integration", response_class=HTMLResponse)
def page_integration(request: Request):
    return templates.TemplateResponse(request, "integration.html", _base_context(request, "integration", "Integration Hub & Audit Log"))
