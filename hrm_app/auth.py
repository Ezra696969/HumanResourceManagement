"""Mekanisme autentikasi token Bearer (gaya OAuth2 client_credentials) dan pencatatan log inbound."""
import secrets
import time
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from hrm_app.config import TOKEN_TTL_SECONDS
from hrm_app.database import db_session

# Penyimpanan token aktif di memori server
ACTIVE_TOKENS: dict[str, dict[str, Any]] = {}


def record_integration_log(
    direction: str,
    partner_key: str,
    method: str,
    url_or_path: str,
    status_code: int,
    latency_ms: int = 0,
    request_summary: str = "",
    response_summary: str = "",
    success: bool = True,
) -> None:
    """Menyimpan jejak audit pertukaran data inbound/outbound ke tabel integration_logs."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO integration_logs (
                timestamp, direction, partner_key, method, url_or_path,
                status_code, latency_ms, request_summary, response_summary, success
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                direction,
                partner_key,
                method,
                url_or_path,
                status_code,
                latency_ms,
                request_summary[:500],
                response_summary[:500],
                1 if success else 0,
            ),
        )


def issue_access_token(client_id: str, client_secret: str) -> dict[str, Any]:
    """Memvalidasi client_id & client_secret pada tabel api_clients dan menerbitkan Bearer token."""
    with db_session() as conn:
        row = conn.execute(
            "SELECT client_id, client_secret, partner_name, allowed_scopes, is_active "
            "FROM api_clients WHERE client_id = ?",
            (client_id,),
        ).fetchone()

    if not row or not row["is_active"]:
        record_integration_log(
            "INBOUND", client_id or "anonim", "POST", "/oauth/token",
            401, 0, f"client_id={client_id}", "Kredensial tidak terdaftar atau nonaktif", False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kredensial client tidak valid atau nonaktif",
        )

    if not secrets.compare_digest(row["client_secret"].encode("utf-8"), client_secret.encode("utf-8")):
        record_integration_log(
            "INBOUND", client_id, "POST", "/oauth/token",
            401, 0, f"client_id={client_id}", "client_secret salah", False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="client_secret salah",
        )

    token = secrets.token_urlsafe(32)
    ACTIVE_TOKENS[token] = {
        "client_id": row["client_id"],
        "partner_name": row["partner_name"],
        "scopes": row["allowed_scopes"],
        "exp": time.time() + TOKEN_TTL_SECONDS,
    }
    record_integration_log(
        "INBOUND", row["client_id"], "POST", "/oauth/token",
        200, 1, f"client_id={client_id}", "Token Bearer berhasil diterbitkan", True,
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": TOKEN_TTL_SECONDS,
        "client_id": row["client_id"],
    }


def verify_bearer_token(request: Request) -> dict[str, Any]:
    """Dependency FastAPI untuk memproteksi endpoint eksternal antar-kelompok."""
    auth_header = request.headers.get("Authorization", "")
    path = str(request.url.path)
    method = request.method

    if not auth_header.startswith("Bearer "):
        record_integration_log(
            "INBOUND", "anonim", method, path, 401, 0,
            "Header Authorization kosong", "Token Bearer tidak ditemukan", False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak ada. Kirim header Authorization: Bearer <token>",
        )

    raw_token = auth_header[len("Bearer "):].strip()
    token_info = ACTIVE_TOKENS.get(raw_token)
    if not token_info or token_info["exp"] < time.time():
        if raw_token in ACTIVE_TOKENS:
            ACTIVE_TOKENS.pop(raw_token, None)
        record_integration_log(
            "INBOUND", "unknown_token", method, path, 401, 0,
            "Bearer token ditolak", "Token tidak valid atau kedaluwarsa", False,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tidak valid atau kedaluwarsa",
        )

    return token_info


def get_current_partner(token_info: dict[str, Any] = Depends(verify_bearer_token)) -> dict[str, Any]:
    """Mengembalikan identitas partner terautentikasi."""
    return token_info
