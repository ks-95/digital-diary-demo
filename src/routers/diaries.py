from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from utils.db import get_db
from utils.security import get_current_user
from controllers import controller
from schemas.dtos import DiaryCreate, DiaryResponse

diaries_router = APIRouter(prefix="/cases/{case_id}/diaries", tags=["Case Diaries"])

@diaries_router.post("/", response_model=DiaryResponse, status_code=status.HTTP_201_CREATED)
async def add_diary_entry(
    case_id: uuid.UUID,
    diary_in: DiaryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    return await controller.add_diary_entry(case_id, diary_in, db, owner_id=owner_id)

@diaries_router.get("/", response_model=List[DiaryResponse])
async def list_case_diaries(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    return await controller.list_case_diaries(case_id, db, owner_id=owner_id)