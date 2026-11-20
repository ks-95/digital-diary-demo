"""Razorpay recurring subscriptions and signature-verified webhooks."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import BillingWebhookEvent, UserSubscription
from models.user import User
from utils.db import get_db
from utils.security import get_current_user
from utils.settings import settings

logger = logging.getLogger(__name__)
billing_router = APIRouter(prefix="/billing", tags=["Billing"])
RAZORPAY_API = "https://api.razorpay.com/v1"
OPEN_SUBSCRIPTION_STATES = ("created", "authenticated", "active", "pending", "halted", "paused", "resumed")
VALID_SUBSCRIPTION_STATES = set(OPEN_SUBSCRIPTION_STATES) | {"cancelled", "completed", "expired"}


def _provider_ready() -> None:
    if not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_PLAN_ID):
        raise HTTPException(status_code=503, detail="Subscription checkout is not configured yet.")


def _user_uuid(user: dict) -> uuid.UUID:
    try:
        return uuid.UUID(str(user.get("sub") or user.get("user_id")))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid account session.")


def _provider_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return None


async def require_active_subscription(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if not settings.BILLING_ENFORCED:
        return
    user_id = _user_uuid(user)
    row = await db.scalar(
        select(UserSubscription.subscription_id)
        .where(UserSubscription.user_id == user_id, UserSubscription.status == "active")
        .limit(1)
    )
    if row is None:
        raise HTTPException(
            status_code=402,
            detail={"code": "subscription_required", "message": "An active officer subscription is required."},
        )
@billing_router.post("/subscribe")
async def create_subscription(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create or resume checkout for the dashboard-configured monthly plan."""
    _provider_ready()
    user_id = _user_uuid(user)
    existing = await db.scalar(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id, UserSubscription.status.in_(OPEN_SUBSCRIPTION_STATES))
        .order_by(UserSubscription.created_at.desc())
        .limit(1)
    )
    if existing and existing.checkout_url:
        return {
            "provider": "razorpay",
            "subscription_id": existing.provider_subscription_id,
            "status": existing.status,
            "checkout_url": existing.checkout_url,
            "reused": True,
        }

    payload = {
        "plan_id": settings.RAZORPAY_PLAN_ID,
        "total_count": max(1, settings.RAZORPAY_TOTAL_COUNT),
        "quantity": 1,
        "customer_notify": False,
        "notes": {"app_user_id": str(user_id), "product": "digital_diary"},
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=8.0)) as client:
            response = await client.post(
                f"{RAZORPAY_API}/subscriptions",
                json=payload,
                auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            )
        if response.status_code not in {200, 201}:
            logger.warning("Razorpay subscription create failed with HTTP %s", response.status_code)
            raise HTTPException(status_code=502, detail="Razorpay could not create subscription checkout.")
        provider_data = response.json()
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Razorpay is temporarily unreachable. Please retry shortly.")

    provider_id = str(provider_data.get("id") or "")
    checkout_url = str(provider_data.get("short_url") or "")
    if not provider_id or not checkout_url:
        logger.error("Razorpay returned an incomplete subscription response.")
        raise HTTPException(status_code=502, detail="Razorpay returned an incomplete checkout response.")

    row = UserSubscription(
        user_id=user_id,
        provider="razorpay",
        provider_subscription_id=provider_id,
        plan_id=settings.RAZORPAY_PLAN_ID,
        checkout_url=checkout_url,
        status=str(provider_data.get("status") or "created"),
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A subscription checkout is already being created. Refresh and retry.")
    return {
        "provider": "razorpay",
        "subscription_id": provider_id,
        "status": row.status,
        "checkout_url": checkout_url,
        "reused": False,
    }


@billing_router.get("/me")
async def my_subscription(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = _user_uuid(user)
    row = await db.scalar(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .order_by(UserSubscription.created_at.desc())
        .limit(1)
    )
    if not row:
        return {"provider": "razorpay", "status": "not_subscribed", "active": False}
    return {
        "provider": row.provider,
        "subscription_id": row.provider_subscription_id,
        "plan_id": row.plan_id,
        "status": row.status,
        "active": row.status == "active",
        "period_start": row.period_start.isoformat() if row.period_start else None,
        "period_end": row.period_end.isoformat() if row.period_end else None,
    }


@billing_router.post("/razorpay/webhook", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    event_header: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
):
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Razorpay webhook verification is not configured.")
    raw_body = await request.body()
    if len(raw_body) > 1024 * 1024:
        raise HTTPException(status_code=413, detail="Webhook payload is too large.")
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    try:
        body = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid webhook JSON.")

    event_type = str(body.get("event") or "")[:80]
    subscription_entity = (((body.get("payload") or {}).get("subscription") or {}).get("entity") or {})
    provider_id = str(subscription_entity.get("id") or "")[:100]
    if not event_type or not provider_id:
        # Ignore valid but unrelated Razorpay events, while acknowledging delivery.
        return {"received": True, "ignored": True}

    event_id = (event_header or hashlib.sha256(raw_body).hexdigest())[:128]
    if await db.get(BillingWebhookEvent, event_id):
        return {"received": True, "duplicate": True}

    subscription = await db.scalar(
        select(UserSubscription).where(UserSubscription.provider_subscription_id == provider_id)
    )
    if subscription is None:
        notes = subscription_entity.get("notes") or {}
        try:
            user_id = uuid.UUID(str(notes.get("app_user_id")))
        except (ValueError, TypeError, AttributeError):
            logger.warning("Verified Razorpay webhook has no matching subscription owner.")
            return {"received": True, "ignored": True}
        if not await db.get(User, user_id):
            return {"received": True, "ignored": True}
        subscription = UserSubscription(
            user_id=user_id,
            provider="razorpay",
            provider_subscription_id=provider_id,
            plan_id=str(subscription_entity.get("plan_id") or settings.RAZORPAY_PLAN_ID)[:100],
            status="created",
        )
        db.add(subscription)
        await db.flush()

    event_created_at = body.get("created_at") or 0
    try:
        event_created_at = int(event_created_at)
    except (TypeError, ValueError):
        event_created_at = 0
    provider_status = str(subscription_entity.get("status") or "").lower()
    if provider_status in VALID_SUBSCRIPTION_STATES and event_created_at >= subscription.last_event_at:
        subscription.status = provider_status
        subscription.last_event_at = event_created_at
        subscription.period_start = _provider_datetime(subscription_entity.get("current_start"))
        subscription.period_end = _provider_datetime(subscription_entity.get("current_end"))
    db.add(BillingWebhookEvent(
        event_id=event_id,
        event_type=event_type,
        provider_subscription_id=provider_id,
    ))
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        return {"received": True, "duplicate": True}
    return {"received": True}

