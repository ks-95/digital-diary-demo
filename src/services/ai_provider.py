"""Gemini-first, OpenAI-fallback provider adapter for document JSON extraction."""
import base64
import logging
from typing import Callable

from fastapi.concurrency import run_in_threadpool

from utils.settings import settings

logger = logging.getLogger(__name__)
_openai_client = None


def _openai_key() -> str:
    return (settings.OPENAI_API_KEY or "").strip()


def _is_transient_provider_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    status = status or getattr(response, "status_code", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    message = str(exc).lower()
    return any(token in message for token in (
        "resource_exhausted", "resource exhausted", "quota", "rate limit",
        "temporarily unavailable", "service unavailable", "deadline exceeded",
        "timed out", "timeout", "overloaded", "high demand", "at capacity", "try again later",
    ))


async def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if not _openai_key():
            raise RuntimeError("OpenAI fallback is not configured. Set OPENAI_API_KEY.")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install the 'openai' package to enable the fallback provider.") from exc
        _openai_client = AsyncOpenAI(api_key=_openai_key(), timeout=75.0, max_retries=0)
    return _openai_client


async def _openai_json(prompt: str, files: list[tuple[str, bytes, str]]) -> str:
    client = await _get_openai_client()
    content = [{"type": "input_text", "text": prompt}]
    for filename, data, mime_type in files:
        encoded = base64.b64encode(data).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        if mime_type.startswith("image/"):
            content.append({"type": "input_image", "image_url": data_url, "detail": "high"})
        else:
            content.append({"type": "input_file", "filename": filename, "file_data": data_url})
    response = await client.responses.create(
        model=settings.OPENAI_MODEL,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}},
        store=False,
    )
    result = response.output_text
    if not result or not result.strip():
        raise RuntimeError("OpenAI returned an empty document extraction.")
    return result


async def generate_document_json(
    prompt: str,
    files: list[tuple[str, bytes, str]],
    gemini_call: Callable[[], str],
    *,
    force_openai: bool = False,
) -> tuple[str, str]:
    """Run preferred provider; in auto mode fail over only for transient Gemini failures."""
    mode = (settings.AI_PROVIDER or "auto").strip().lower()
    if force_openai or mode == "openai":
        return await _openai_json(prompt, files), "openai"

    has_gemini = bool((settings.GEMINI_API_KEY or "").strip())
    if not has_gemini:
        if mode == "auto" and _openai_key():
            logger.warning("Gemini is not configured; using configured OpenAI provider.")
            return await _openai_json(prompt, files), "openai"
        raise RuntimeError("No AI provider is configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")

    try:
        return await run_in_threadpool(gemini_call), "gemini"
    except Exception as exc:
        if mode == "auto" and _openai_key() and _is_transient_provider_error(exc):
            logger.warning("Gemini extraction temporarily failed; retrying through OpenAI: %s", str(exc)[:240])
            return await _openai_json(prompt, files), "openai"
        raise


def generate_text_sync_with_fallback(gemini_call: Callable[[], str], prompt: str) -> tuple[str, str]:
    """Synchronous counterpart used by existing thread-pooled report generation."""
    mode = (settings.AI_PROVIDER or "auto").strip().lower()
    if mode == "openai":
        return _openai_sync_json(prompt), "openai"
    if not (settings.GEMINI_API_KEY or "").strip():
        if mode == "auto" and _openai_key():
            return _openai_sync_json(prompt), "openai"
        raise RuntimeError("No AI provider is configured. Set GEMINI_API_KEY or OPENAI_API_KEY.")
    try:
        return gemini_call(), "gemini"
    except Exception as exc:
        if mode == "auto" and _openai_key() and _is_transient_provider_error(exc):
            logger.warning("Gemini report generation temporarily failed; retrying through OpenAI: %s", str(exc)[:240])
            return _openai_sync_json(prompt), "openai"
        raise


def _openai_sync_json(prompt: str) -> str:
    if not _openai_key():
        raise RuntimeError("OpenAI provider is not configured. Set OPENAI_API_KEY.")
    from openai import OpenAI
    client = OpenAI(api_key=_openai_key(), timeout=75.0, max_retries=0)
    response = client.responses.create(
        model=settings.OPENAI_MODEL,
        input=prompt,
        text={"format": {"type": "json_object"}},
        store=False,
    )
    if not response.output_text:
        raise RuntimeError("OpenAI returned an empty report response.")
    return response.output_text


async def close_ai_provider_clients() -> None:
    global _openai_client
    if _openai_client is not None:
        await _openai_client.close()
        _openai_client = None
