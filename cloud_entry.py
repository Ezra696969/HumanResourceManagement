"""Entrypoint Cloud Terpadu (1 Port) untuk Deploy 24/7 di Render, Railway, Docker, atau Vercel."""
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request

from hrm_app.database import db_session
from hrm_app.main import create_app
from hrm_app.seed_data import seed_database
from mocks.mock_crm import app as crm_app
from mocks.mock_keuangan import app as fin_app
from mocks.mock_scm import app as scm_app


def _configure_unified_urls(self_base: str) -> None:
    """Mengarahkan default URL partner & HRM_BASE_URL ke gateway terpadu satu port."""
    base = self_base.rstrip("/")
    os.environ["HRM_BASE_URL"] = base
    with db_session() as conn:
        for key in ("keuangan", "crm", "scm"):
            row = conn.execute(
                "SELECT base_url FROM integration_partners WHERE partner_key = ?", (key,)
            ).fetchone()
            if row and (
                row["base_url"].startswith("http://127.0.0.1:500")
                or row["base_url"].startswith("http://localhost:500")
                or "/mock/" in row["base_url"]
            ):
                conn.execute(
                    "UPDATE integration_partners SET base_url = ? WHERE partner_key = ?",
                    (f"{base}/mock/{key}", key),
                )


def _initial_cloud_base() -> str:
    port = os.environ.get("PORT", "8000")
    return f"http://127.0.0.1:{port}"


@asynccontextmanager
async def cloud_lifespan(app: FastAPI):
    os.environ["CLOUD_UNIFIED_MODE"] = "1"
    seed_database(theme_key="manufaktur", force_reset=False)
    if not os.environ.get("VERCEL"):
        _configure_unified_urls(_initial_cloud_base())
    yield


def create_cloud_app() -> FastAPI:
    base_app = create_app()
    base_app.router.lifespan_context = cloud_lifespan
    base_app.mount("/mock/keuangan", fin_app)
    base_app.mount("/mock/crm", crm_app)
    base_app.mount("/mock/scm", scm_app)

    @base_app.middleware("http")
    async def sync_vercel_host_middleware(request: Request, call_next):
        if os.environ.get("VERCEL"):
            seed_database(theme_key="manufaktur", force_reset=False)
            host = request.headers.get("host")
            if host:
                proto = request.headers.get("x-forwarded-proto", request.url.scheme or "https")
                _configure_unified_urls(f"{proto}://{host}")
        return await call_next(request)

    return base_app


app = create_cloud_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"[Cloud Unified Demo] http://127.0.0.1:{port}")
    uvicorn.run("cloud_entry:app", host="0.0.0.0", port=port, reload=False)
