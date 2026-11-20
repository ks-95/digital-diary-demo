# src/routers/chargesheet.py
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from utils.db import get_db
from utils.security import get_current_user
from controllers import controller
from controllers.controller import extract_owner_id

chargesheet_router = APIRouter(prefix="/cases/{case_id}/chargesheet", tags=["Chargesheet Generation"])


@chargesheet_router.get("/generate")
@chargesheet_router.post("/generate")
async def generate_chargesheet(
    case_id: uuid.UUID,
    cs_number: Optional[str] = Query(None, description="Charge sheet No. as allotted by the station, e.g. 13/2025"),
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = extract_owner_id(user)
    return await controller.generate_chargesheet(case_id, db, cs_number, owner_id=owner_id)