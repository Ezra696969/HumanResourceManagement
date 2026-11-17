"""Entrypoint utama FastAPI untuk Sistem HRM Kelompok 12 (Port 5000)."""
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from hrm_app.config import HRM_PORT
from hrm_app.routers.api_v1 import router as api_router
from hrm_app.routers.web import web_router
from hrm_app.seed_data import seed_database


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Memastikan skema SQLite dan data preset awal siap saat server menyala."""
    seed_database(theme_key="manufaktur", force_reset=False)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Sistem HRM Terintegrasi — Kelompok 12 (IAK)",
        description=(
            "Aplikasi Human Resource Management (HRM) untuk Proyek UAS Integrasi Aplikasi Korporat. "
            "Dilengkapi REST API Provider (OAuth Bearer) untuk Kelompok 2 (Keuangan), Kelompok 7 (CRM), "
            "dan Kelompok 8 (SCM), serta Integration Adapter untuk menarik data komisi/lembur dan mengirim payroll."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.include_router(api_router)
    app.include_router(web_router)
    return app


app = create_app()


if __name__ == "__main__":
    print(f"[HRM Kel. 12] Menjalankan server di http://127.0.0.1:{HRM_PORT} (Swagger: /docs)")
    uvicorn.run("hrm_app.main:app", host="0.0.0.0", port=HRM_PORT, reload=False)
