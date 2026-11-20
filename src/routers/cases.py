from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List
import uuid
import mimetypes

from controllers import controller
from schemas.dtos import CaseCreate, CaseResponse
from utils.db import get_db
from utils.security import get_current_user
from models.models import Case, CaseEvidence
from services.evidence_storage import create_evidence_download_url, local_evidence_path

case_routes = APIRouter(prefix="/cases", tags=["Cases"])

@case_routes.post("/new_case")
async def lodge_case(
    case_in: CaseCreate,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if not case_in.io_name:
        case_in.io_name = user.get("name") or None
    if not case_in.police_station:
        case_in.police_station = user.get("station") or None
    owner_id = controller.extract_owner_id(user)
    return await controller.create_case(case_in, db, owner_id=owner_id)

@case_routes.get("/", response_model=List[CaseResponse])
async def list_case(
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    return await controller.list_cases(db=db, owner_id=owner_id)

@case_routes.get("/{case_id}", response_model=CaseResponse)
async def get_case(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    return await controller.get_case(case_id, db=db, owner_id=owner_id)

@case_routes.get("/{case_id}/evidence", response_model=List[dict])
async def list_case_evidence(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    case_stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        case_stmt = case_stmt.where(Case.owner_id == owner_id)
    case_obj = (await db.execute(case_stmt)).scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found or access denied.")

    stmt = select(CaseEvidence).where(CaseEvidence.case_id == case_id, CaseEvidence.record_category == "EVIDENCE").order_by(CaseEvidence.uploaded_at.desc())
    res = await db.execute(stmt)
    evidence_list = res.scalars().all()

    return [
        {
            "evidence_id": str(e.evidence_id),
            "artifact_type": e.artifact_type,
            "title": e.title,
            "record_category": e.record_category,
            "extracted_details": e.extracted_details or {},
            "original_filename": e.original_filename,
            "uploaded_at": str(e.uploaded_at),
        }
        for e in evidence_list
    ]


@case_routes.get("/{case_id}/case-files", response_model=List[dict])
async def list_case_files(
    case_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    case_stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        case_stmt = case_stmt.where(Case.owner_id == owner_id)
    case_obj = (await db.execute(case_stmt)).scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found or access denied.")
    res = await db.execute(
        select(CaseEvidence).where(CaseEvidence.case_id == case_id, CaseEvidence.record_category == "CASE_DOCUMENT").order_by(CaseEvidence.uploaded_at.desc())
    )
    return [
        {
            "evidence_id": str(item.evidence_id),
            "artifact_type": item.artifact_type,
            "title": item.title,
            "record_category": item.record_category,
            "extracted_details": item.extracted_details or {},
            "original_filename": item.original_filename,
            "uploaded_at": str(item.uploaded_at),
        }
        for item in res.scalars().all()
    ]


@case_routes.get("/{case_id}/case-files/{file_id}/download")
async def download_case_file(
    case_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    owner_id = controller.extract_owner_id(user)
    case_stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        case_stmt = case_stmt.where(Case.owner_id == owner_id)
    if not (await db.execute(case_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Case not found or access denied.")
    res = await db.execute(select(CaseEvidence).where(
        CaseEvidence.evidence_id == file_id,
        CaseEvidence.case_id == case_id,
    ))
    record = res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Case file not found.")
    if record.file_path.startswith("supabase://"):
        try:
            signed_url = await create_evidence_download_url(record.file_path)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Stored case file is temporarily unavailable: {str(exc)[:160]}")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(signed_url, status_code=307, headers={"Cache-Control": "no-store"})

    resolved = local_evidence_path(record.file_path)
    if resolved is None or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Stored case file is unavailable.")
    return FileResponse(
        str(resolved),
        filename=record.original_filename or resolved.name,
        media_type=mimetypes.guess_type(str(resolved))[0] or "application/octet-stream",
    )
