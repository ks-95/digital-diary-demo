import hashlib
import json
import uuid
from datetime import date
from typing import Optional, Dict, Any

from fastapi import HTTPException, status
from starlette.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from models.models import Case, CaseDiary
from schemas.dtos import CaseCreate, DiaryCreate
from services.ai_services import generate_chargesheet_data
from services.rag_service import retrieve_case_context
from services.doc_generator import build_chargesheet_docx


def calculate_sha256(data_str: str) -> str:
    return hashlib.sha256(data_str.encode('utf-8')).hexdigest()


def extract_owner_id(user: Optional[dict]) -> Optional[str]:
    """Extracts a consistent unique officer identifier from the JWT user dict."""
    if not user:
        return None
    val = (
        user.get("user_id")
        or user.get("id")
        or user.get("sub")
        or user.get("mobile_number")
        or user.get("mobile")
    )
    return str(val) if val is not None else None


async def create_case(body: CaseCreate, db: AsyncSession, owner_id: Optional[str] = None):
    # Check duplicate crime number
    stmt = select(Case).where(Case.crime_number == body.crime_number)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Crime number '{body.crime_number}' already exists in records."
        )

    # 1. Instantiate and add Case with explicit UUID and owner_id
    case_id = uuid.uuid4()
    new_case = Case(
        case_id=case_id,
        owner_id=owner_id,
        crime_number=body.crime_number,
        fir_number=body.fir_number,
        police_station=body.police_station,
        district=body.district,
        io_name=body.io_name,
        complainant_father=body.complainant_father,
        complaint_date=body.complaint_date,
        complainant_name=body.complainant_name,
        complainant_address=body.complainant_address,
        complainant_phone=body.complainant_phone,
        offense_sections=body.offense_sections,
        stolen_property_value=body.stolen_property_value,
        complaint_summary=body.complaint_summary,
        investigation_domain=body.investigation_domain.upper() if body.investigation_domain.upper() in {"CYBER", "NON_CYBER"} else "UNCLASSIFIED",
    )
    db.add(new_case)

    # 2. Automatically generate Day-1 Initial Case Diary
    diary_summary = body.initial_diary_summary or (
        f"FIR registered under legal sections: {', '.join(body.offense_sections)}. "
        f"Complainant {body.complainant_name} reported: "
        f"{body.complaint_summary or 'Case instituted on basis of formal complaint.'}"
    )
    diary_action = body.initial_action_taken or (
        "Registered the First Information Report and took up investigation as per the facts and applicable law."
    )
    tech_artifacts = body.tech_artifacts or {}

    raw_payload = f"{case_id}:{diary_summary}:{diary_action}:{json.dumps(tech_artifacts, sort_keys=True)}"
    entry_hash = calculate_sha256(raw_payload)

    initial_diary = CaseDiary(
        diary_id=uuid.uuid4(),
        case_id=case_id,
        entry_date=body.complaint_date or date.today(),
        investigation_summary=diary_summary,
        action_taken=diary_action,
        tech_artifacts_obtained=tech_artifacts,
        entry_hash=entry_hash,
        is_locked=False,
    )
    db.add(initial_diary)

    await db.commit()
    try:
        await db.refresh(new_case)
        await db.refresh(initial_diary)
    except Exception:
        pass

    return {
        "status": "new case is lodged successfully....",
        "data": new_case,
        "initial_diary": initial_diary,
        "case_id": str(new_case.case_id),
        "crime_number": new_case.crime_number,
        "fir_number": new_case.fir_number,
    }


async def list_cases(db: AsyncSession, owner_id: Optional[str] = None):
    stmt = select(Case)
    if owner_id:
        stmt = stmt.where(Case.owner_id == owner_id)
    stmt = stmt.order_by(Case.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


async def get_case(case_id: uuid.UUID, db: AsyncSession, owner_id: Optional[str] = None):
    stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        stmt = stmt.where(Case.owner_id == owner_id)
    result = await db.execute(stmt)
    case_obj = result.scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found or access denied.")
    return case_obj


async def generate_chargesheet(
    case_id: uuid.UUID,
    db: AsyncSession,
    cs_number: Optional[str] = None,
    owner_id: Optional[str] = None,
):
    stmt = select(Case).options(selectinload(Case.diaries), selectinload(Case.evidence)).where(Case.case_id == case_id)
    if owner_id:
        stmt = stmt.where(Case.owner_id == owner_id)
    res = await db.execute(stmt)
    case_obj = res.scalar_one_or_none()

    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found or access denied.")

    if not case_obj.diaries:
        raise HTTPException(status_code=400, detail="Cannot generate chargesheet without diary entries.")

    case_dict = {
        "crime_number": case_obj.crime_number,
        "fir_number": case_obj.fir_number,
        "police_station": case_obj.police_station or "",
        "district": case_obj.district or "",
        "io_name": case_obj.io_name or "",
        "complainant_name": case_obj.complainant_name,
        "complainant_father": case_obj.complainant_father or "",
        "complainant_address": case_obj.complainant_address or "",
        "offense_sections": case_obj.offense_sections,
        "complaint_date": case_obj.complaint_date.strftime("%d.%m.%Y") if case_obj.complaint_date else "",
        "stolen_property_value": case_obj.stolen_property_value or "",
        "complaint_summary": case_obj.complaint_summary or "",
        "investigation_domain": case_obj.investigation_domain,
        "case_files": [],
        "cs_number": (cs_number or "").strip(),
    }

    diary_list = [
        {
            "entry_date": d.entry_date.strftime("%d.%m.%Y"),
            "investigation_summary": d.investigation_summary,
            "action_taken": d.action_taken,
            "tech_artifacts": d.tech_artifacts_obtained,
            "dsr_number": d.dsr_number,
        }
        for d in case_obj.diaries
    ]

    retrieved = await retrieve_case_context(
        db, case_id,
        ["FIR allegations and particulars", "accused identity address arrest custody",
         "witness statements examination", "seizure articles PR number seized from",
         "court custody prayer order", "malkhana deposit seal CMR", "certificate report and forensic result",
         "transaction account number mobile IMEI dates sections"],
        limit=36,
    )
    # Don't hold a PostgreSQL pool connection during the comparatively slow LLM call.
    await db.commit()
    case_files = [{"category": "RETRIEVED_CASE_SOURCE", **item} for item in retrieved]
    if not case_files:
        case_files = [
            {"category": e.record_category, "type": e.artifact_type, "title": e.title,
             "details": e.extracted_details or {}, "uploaded_at": e.uploaded_at}
            for e in case_obj.evidence
        ]

    try:
        case_dict.pop("case_files", None)
        ai_structured_report = await run_in_threadpool(generate_chargesheet_data, case_dict, diary_list, case_files)
        docx_file_path = build_chargesheet_docx(case_dict, ai_structured_report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Chargesheet generation failed: {str(e)}")

    clean_crime_no = case_obj.crime_number.replace("/", "_").replace("\\", "_")
    return FileResponse(
        path=docx_file_path,
        filename=f"Chargesheet_{clean_crime_no}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


async def add_diary_entry(
    case_id: uuid.UUID,
    diary_in: DiaryCreate,
    db: AsyncSession,
    owner_id: Optional[str] = None,
):
    # Verify Case exists and belongs to the logged-in officer
    case_stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        case_stmt = case_stmt.where(Case.owner_id == owner_id)
    res = await db.execute(case_stmt)
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Case not found or access denied.")

    artifacts = diary_in.tech_artifacts_obtained or {}
    raw_payload = f"{case_id}:{diary_in.entry_date}:{diary_in.diary_entry_time}:{diary_in.investigation_summary}:{diary_in.action_taken}:{json.dumps(artifacts, sort_keys=True)}"
    entry_hash = calculate_sha256(raw_payload)

    new_entry = CaseDiary(
        case_id=case_id,
        entry_date=diary_in.entry_date or date.today(),
        diary_entry_time=diary_in.diary_entry_time,
        investigation_summary=diary_in.investigation_summary,
        action_taken=diary_in.action_taken,
        tech_artifacts_obtained=artifacts,
        entry_hash=entry_hash,
        is_locked=False,
        dsr_number=getattr(diary_in, 'dsr_number', None),
        arrested_accused=diary_in.arrested_accused,
        bailed_accused=diary_in.bailed_accused,
        at_large_accused=diary_in.at_large_accused,
    )
    db.add(new_entry)
    await db.commit()
    await db.refresh(new_entry)
    return new_entry


async def list_case_diaries(case_id: uuid.UUID, db: AsyncSession, owner_id: Optional[str] = None):
    if owner_id:
        case_stmt = select(Case.case_id).where(Case.case_id == case_id, Case.owner_id == owner_id)
        if not (await db.execute(case_stmt)).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Case not found or access denied.")

    stmt = select(CaseDiary).where(CaseDiary.case_id == case_id).order_by(CaseDiary.entry_timestamp.asc())
    res = await db.execute(stmt)
    return res.scalars().all()
