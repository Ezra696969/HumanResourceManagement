"""Konfigurasi dasar aplikasi HRM Kelompok 12."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
if os.environ.get("VERCEL"):
    DATA_DIR = Path("/tmp/hrm_kel12_data")
else:
    DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

HRM_DB_PATH = Path(os.environ.get("HRM_DB_PATH", str(DATA_DIR / "hrm_kel12.db")))
HRM_PORT = int(os.environ.get("HRM_PORT", "5000"))
TOKEN_TTL_SECONDS = int(os.environ.get("HRM_TOKEN_TTL", "3600"))
DEFAULT_PERIOD = os.environ.get("HRM_DEFAULT_PERIOD", "2026-11")
