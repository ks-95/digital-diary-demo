"""Private evidence storage with local development and Supabase Storage backends."""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import httpx

from utils.settings import settings


def _root() -> Path:
    root = Path(settings.EVIDENCE_STORAGE_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _supabase_headers(content_type: str = "application/json") -> dict[str, str]:
    if not settings.SUPABASE_URL:
        raise RuntimeError("Supabase Storage requires SUPABASE_URL and a server-side Supabase secret key.")

    # Prefer Supabase's current opaque secret key. It belongs in the apikey
    # header only; it is not a JWT and must not be sent as a Bearer token.
    secret_key = (settings.SUPABASE_SECRET_KEY or "").strip()
    if secret_key:
        if not secret_key.startswith("sb_secret_"):
            raise RuntimeError("SUPABASE_SECRET_KEY must be a Supabase sb_secret_ key.")
        return {"apikey": secret_key, "Content-Type": content_type}

    # Backward compatibility for existing installs using the legacy JWT key.
    service_role_key = (settings.SUPABASE_SERVICE_ROLE_KEY or "").strip()
    if not service_role_key:
        raise RuntimeError("Supabase Storage requires SUPABASE_SECRET_KEY (recommended) or the legacy SUPABASE_SERVICE_ROLE_KEY.")
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": content_type,
    }


def _storage_object_path(storage_ref: str) -> tuple[str, str]:
    if not storage_ref.startswith("supabase://"):
        raise ValueError("This file is not stored in Supabase Storage.")
    bucket_and_key = storage_ref[len("supabase://"):]
    bucket, sep, key = bucket_and_key.partition("/")
    if not sep or not bucket or not key:
        raise ValueError("Invalid Supabase Storage reference.")
    return bucket, key


async def store_evidence(data: bytes, object_name: str, content_type: str) -> str:
    """Persist evidence and return the opaque database reference."""
    if settings.STORAGE_BACKEND.strip().lower() == "supabase":
        bucket = settings.SUPABASE_STORAGE_BUCKET.strip()
        key = object_name.lstrip("/")
        url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        headers = _supabase_headers(content_type)
        headers["x-upsert"] = "false"
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(url, content=data, headers=headers)
        if response.status_code not in {200, 201}:
            raise RuntimeError(f"Supabase Storage upload failed (HTTP {response.status_code}).")
        return f"supabase://{bucket}/{key}"

    if settings.STORAGE_BACKEND.strip().lower() != "local":
        raise RuntimeError("STORAGE_BACKEND must be 'local' or 'supabase'.")
    root = _root()
    target = (root / Path(object_name).name).resolve()
    if target.parent != root:
        raise ValueError("Invalid evidence filename.")
    target.write_bytes(data)
    return os.path.relpath(target, Path.cwd())


def local_evidence_path(storage_ref: str) -> Path | None:
    """Resolve a legacy or local evidence reference, rejecting path traversal."""
    if storage_ref.startswith("supabase://"):
        return None
    candidate = Path(storage_ref)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    candidate = candidate.resolve()
    root = _root()
    try:
        if os.path.commonpath([str(root), str(candidate)]) != str(root):
            return None
    except ValueError:
        return None
    return candidate


async def create_evidence_download_url(storage_ref: str, expires_in: int = 90) -> str:
    bucket, key = _storage_object_path(storage_ref)
    url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(key, safe='/')}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        response = await client.post(
            url,
            json={"expiresIn": expires_in},
            headers=_supabase_headers(),
        )
    if response.status_code not in {200, 201}:
        raise RuntimeError(f"Supabase Storage could not sign the download (HTTP {response.status_code}).")
    signed_path = response.json().get("signedURL")
    if not signed_path:
        raise RuntimeError("Supabase Storage returned no signed download URL.")
    if signed_path.startswith("http://") or signed_path.startswith("https://"):
        return signed_path
    if signed_path.startswith("/storage/v1/"):
        return f"{settings.SUPABASE_URL.rstrip('/')}{signed_path}"
    return f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1{signed_path if signed_path.startswith('/') else f'/{signed_path}'}"


async def delete_evidence(storage_ref: str) -> None:
    if storage_ref.startswith("supabase://"):
        bucket, key = _storage_object_path(storage_ref)
        url = f"{settings.SUPABASE_URL.rstrip('/')}/storage/v1/object/{quote(bucket, safe='')}"
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            response = await client.request("DELETE", url, json={"prefixes": [key]}, headers=_supabase_headers())
        if response.status_code not in {200, 204}:
            raise RuntimeError(f"Supabase Storage delete failed (HTTP {response.status_code}).")
        return
    path = local_evidence_path(storage_ref)
    if path is not None:
        path.unlink(missing_ok=True)

