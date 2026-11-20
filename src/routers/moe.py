import re
import uuid
import hashlib
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from utils.db import get_db
from models.models import Case, CaseDiary, CaseEvidence
from controllers.controller import extract_owner_id
from utils.security import get_current_user
from services.moe_generator import build_moe_docx
from services.evidence_storage import store_evidence, delete_evidence

moe_router = APIRouter(tags=["Memo of Evidence"])

ALLOWED_EXT = {".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png"}
MAX_BYTES = 15 * 1024 * 1024


@moe_router.get("/cases/{case_id}/moe/download")
async def generate_moe(case_id: uuid.UUID, dsr_number: str = Query(...), db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    """MoE is allowed only when a DSR number is supplied."""
    dsr = (dsr_number or "").strip()
    if not dsr:
        raise HTTPException(status_code=400, detail="DSR number is required to generate a Memo of Evidence.")
    stmt = select(Case).options(selectinload(Case.diaries)).where(Case.case_id == case_id)
    owner_id = extract_owner_id(user)
    if owner_id:
        stmt = stmt.where(Case.owner_id == owner_id)
    res = await db.execute(stmt)
    case = res.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Case not found.")

    case_dict = {
        "fir_number": case.fir_number,
        "complainant_name": case.complainant_name,
        "complainant_address": case.complainant_address,
        "offense_sections": case.offense_sections,
        "complaint_date": case.complaint_date.strftime("%d.%m.%Y") if case.complaint_date else "",
        "complaint_summary": case.complaint_summary,
        "police_station": case.police_station,
        "district": case.district,
        "io_name": case.io_name,
    }
    diaries = [{"entry_date": str(d.entry_date), "investigation_summary": d.investigation_summary} for d in case.diaries]
    path = build_moe_docx(case_dict, diaries, dsr)
    generated_bytes = Path(path).read_bytes()
    storage_ref = f"{case_id}/documents/{uuid.uuid4()}.docx"
    safe_dsr = re.sub(r"[^A-Za-z0-9_-]", "_", dsr)
    try:
        storage_ref = await store_evidence(
            generated_bytes,
            storage_ref,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        db.add(CaseEvidence(
            evidence_id=uuid.uuid4(),
            case_id=case_id,
            artifact_type="MEMO_OF_EVIDENCE",
            record_category="CASE_DOCUMENT",
            title=f"Memo of Evidence - DSR {dsr}"[:255],
            original_filename=f"MoE_DSR_{safe_dsr}.docx"[:255],
            extracted_details={"dsr_number": dsr},
            file_path=storage_ref,
            file_hash=hashlib.sha256(generated_bytes).hexdigest(),
        ))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        try:
            await delete_evidence(storage_ref)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Could not save the Memo of Evidence to the case file: {exc}")
    return Response(
        content=generated_bytes,
        headers={"Content-Disposition": f'attachment; filename="MoE_DSR_{safe_dsr}.docx"'},
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@moe_router.post("/cases/{case_id}/diaries/{diary_id}/moe-upload")
async def upload_moe(case_id: uuid.UUID, diary_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: dict = Depends(get_current_user)):
    """Attach an existing MoE file to a diary entry (only if that entry has a DSR number)."""
    case_stmt = select(Case).where(Case.case_id == case_id)
    owner_id = extract_owner_id(user)
    if owner_id:
        case_stmt = case_stmt.where(Case.owner_id == owner_id)
    if not (await db.execute(case_stmt)).scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Case not found or access denied.")
    res = await db.execute(select(CaseDiary).where(CaseDiary.diary_id == diary_id, CaseDiary.case_id == case_id))
    diary = res.scalar_one_or_none()
    if not diary:
        raise HTTPException(status_code=404, detail="Diary entry not found.")
    if not (diary.dsr_number or "").strip():
        raise HTTPException(status_code=400, detail="MoE can be attached only to an entry that has a DSR number.")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXT))}")
    data = await file.read()
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File is empty or larger than 15 MB.")

    safe_original = Path(file.filename or f"memo{ext}").name[:255]
    storage_ref = f"{case_id}/documents/{uuid.uuid4()}{ext}"
    try:
        storage_ref = await store_evidence(
            data,
            storage_ref,
            mimetypes.guess_type(safe_original)[0] or "application/octet-stream",
        )
        diary.moe_file_path = storage_ref
        db.add(CaseEvidence(
            evidence_id=uuid.uuid4(),
            case_id=case_id,
            artifact_type="MEMO_OF_EVIDENCE",
            record_category="CASE_DOCUMENT",
            title=f"Attached Memo of Evidence - DSR {diary.dsr_number}"[:255],
            original_filename=safe_original,
            extracted_details={"dsr_number": diary.dsr_number, "diary_id": str(diary_id)},
            file_path=storage_ref,
            file_hash=hashlib.sha256(data).hexdigest(),
        ))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        try:
            await delete_evidence(storage_ref)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Could not attach the Memo of Evidence to the case: {exc}")
    return {"status": "attached", "diary_id": str(diary_id), "dsr_number": diary.dsr_number, "file": safe_original}
