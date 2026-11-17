"""Launcher satu klik untuk menyalakan HRM (5000) + 3 Mock Server (5001, 5002, 5003)."""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SERVICES = [
    ("HRM Kel. 12 (UTAMA)", [sys.executable, "-m", "uvicorn", "hrm_app.main:app", "--host", "127.0.0.1", "--port", "5000"], "http://127.0.0.1:5000"),
    ("Mock Keuangan Kel. 2", [sys.executable, "-m", "uvicorn", "mocks.mock_keuangan:app", "--host", "127.0.0.1", "--port", "5001"], "http://127.0.0.1:5001"),
    ("Mock CRM Kel. 7", [sys.executable, "-m", "uvicorn", "mocks.mock_crm:app", "--host", "127.0.0.1", "--port", "5002"], "http://127.0.0.1:5002"),
    ("Mock SCM Kel. 8", [sys.executable, "-m", "uvicorn", "mocks.mock_scm:app", "--host", "127.0.0.1", "--port", "5003"], "http://127.0.0.1:5003"),
]


def main() -> None:
    procs: list[tuple[str, subprocess.Popen]] = []
    print("=" * 65)
    print("  MENJALANKAN EKOSISTEM UAS IAK — FOKUS HRM KELOMPOK 12")
    print("=" * 65)
    try:
        for name, cmd, url in SERVICES:
            p = subprocess.Popen(cmd, cwd=str(ROOT))
            procs.append((name, p))
            print(f"[START] {name:<24} -> {url}")
            time.sleep(0.4)

        print("-" * 65)
        print("  Buka Web HRM Utama : http://127.0.0.1:5000")
        print("  Buka Swagger API   : http://127.0.0.1:5000/docs")
        print("  Tekan Ctrl+C untuk menghentikan semua server.")
        print("-" * 65)

        while True:
            time.sleep(1)
            for name, p in procs:
                if p.poll() is not None:
                    raise RuntimeError(f"Service '{name}' berhenti dengan kode {p.returncode}")
    except (KeyboardInterrupt, RuntimeError) as exc:
        print(f"\n[STOP] Menghentikan semua server ({exc})...")
    finally:
        for _, p in procs:
            if p.poll() is None:
                p.terminate()
        for _, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[DONE] Semua proses dihentikan.")


if __name__ == "__main__":
    main()
