import io
import re
import uuid
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from controllers.controller import extract_owner_id
from models.models import Case, CaseDiary, CaseEvidence
from services.doc_generator import _fmt_date, _fmt_sections, split_sections
from services.fir_time import fir_entry_time_from_sources
from utils.db import get_db
from utils.security import get_current_user

diary_export_router = APIRouter(prefix="/cases", tags=["Case Diary Export"])

ROMAN_NUMS = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
              "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
              "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX"]
IST = timezone(timedelta(hours=5, minutes=30))


def int_to_roman(n: int) -> str:
    return ROMAN_NUMS[n - 1] if 1 <= n <= len(ROMAN_NUMS) else str(n)


def _hhmm(ts: Optional[datetime]) -> str:
    """Time the entry was recorded in the app (IST)."""
    if not ts:
        return ""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(IST).strftime("%H:%M") + " hrs"


def _diary_sections(sections) -> str:
    """Sample style: '318(4)/319(2)/61(2) BNS, 66D IT Act'."""
    g = split_sections(sections or [])
    parts = []
    if g["BNS"]:
        parts.append("/".join(g["BNS"]) + " BNS")
    if g["IPC"]:
        parts.append("/".join(g["IPC"]) + " IPC")
    if g["IT Act"]:
        parts.append("/".join(g["IT Act"]) + " IT Act")
    parts += g["Other"]
    return ", ".join(parts)


def _fir_opening_particular(metadata: dict, source_text: str, key: str, aliases: tuple[str, ...], label: str) -> str:
    """Return an explicitly extracted FIR particular, with a verbatim text fallback."""
    value = next((metadata.get(name) for name in aliases if metadata.get(name)), None)
    if value:
        return str(value).strip()

    # Some OCR/model responses preserve Point 12 text but omit the structured
    # metadata. Recover only a clearly labelled line; never guess from prose.
    labels = {
        "P.O.": r"(?:P\.?\s*O\.?|place\s+of\s+occurrence)",
        "D.O.": r"(?:D\.?\s*O\.?|date\s+of\s+occurrence)",
        "D.R.": r"(?:D\.?\s*R\.?|date\s+of\s+report)",
        "R.O.": r"(?:R\.?\s*O\.?|reporting\s+officer)",
        "I.O.": r"(?:I\.?\s*O\.?|investigating\s+officer)",
    }
    match = re.search(rf"(?im)^\s*{labels[label]}\s*[-:–]\s*(.*?)\s*$", source_text or "")
    return match.group(1).strip() if match else ""


def _fir_opening_narrative(metadata: dict, fir_text: str) -> str:
    """Prepend FIR opening particulars while keeping the extracted FIR text intact."""
    fields = (
        ("P.O.", ("place_of_occurrence", "po", "occurrence_place")),
        ("D.O.", ("date_of_occurrence", "do", "occurrence_datetime")),
        ("D.R.", ("date_of_report", "dr", "information_received_datetime")),
        ("R.O.", ("reporting_officer", "ro", "person_reporting")),
        ("I.O.", ("investigating_officer", "io")),
    )
    lines = ["This time opened the C.D. for the purpose of investigation."]
    lines.extend(
        f"{label}- {value}"
        for label, aliases in fields
        if (value := _fir_opening_particular(metadata, fir_text, label, aliases, label))
    )
    lines.extend([
        "",
        "On careful perusal of the gist of the case, the following particulars of enquiry recorded in the FIR are reproduced verbatim:",
        "",
        fir_text.strip(),
    ])
    return "\n".join(lines).strip()


def build_context(case: Case, diaries: list, evidences: list | None = None) -> dict:
    ps = (case.police_station or "").strip()
    district = (case.district or "").strip()
    io = (case.io_name or "").strip()
    evidences = evidences or []
    fir_evidence = next((e for e in evidences if str(e.artifact_type or "").upper() == "FIR"), None)
    fir_details = fir_evidence.extracted_details if fir_evidence and isinstance(fir_evidence.extracted_details, dict) else {}
    fir_source_text = fir_details.get("source_text") or ""
    fir_diary = next((d for d in diaries
                      if isinstance(d.tech_artifacts_obtained, dict)
                      and (d.tech_artifacts_obtained.get("is_fir_initial_entry") or d.tech_artifacts_obtained.get("fir_metadata"))), None)
    fir_diary_details = fir_diary.tech_artifacts_obtained if fir_diary else {}
    fir_metadata = {}
    if isinstance(fir_details.get("fir_metadata"), dict):
        fir_metadata.update(fir_details["fir_metadata"])
    if isinstance(fir_diary_details.get("fir_metadata"), dict):
        fir_metadata.update(fir_diary_details["fir_metadata"])
    fir_source_text = fir_source_text or (fir_diary.investigation_summary if fir_diary else "")
    # Do not reuse fir_entry_time persisted by older scanner versions: those
    # versions could have derived it from the information-received field.
    # Only the explicitly labelled FIR registration value is authoritative.
    fir_entry_time = fir_entry_time_from_sources(fir_metadata, fir_source_text)
    by_date = {}
    for d in diaries:
        by_date.setdefault(d.entry_date, []).append(d)
    daily_groups = sorted(by_date.items(), key=lambda pair: pair[0])
    out = []
    for idx, (entry_date, day_entries) in enumerate(daily_groups, start=1):
        def _entry_time(item):
            details = item.tech_artifacts_obtained or {}
            if fir_diary and item.diary_id == fir_diary.diary_id:
                # Use the FIR registration field for the FIR entry; never
                # substitute information-received or upload timestamps.
                return fir_entry_time
            return str(item.diary_entry_time or _hhmm(item.entry_timestamp)).strip()

        def _entry_sort(item):
            raw_time = _entry_time(item).upper().replace("HRS", "").strip()
            if fir_diary and item.diary_id == fir_diary.diary_id and not raw_time:
                return (-1, 0)
            for fmt in ("%H:%M", "%H.%M", "%I:%M %p", "%I.%M %p", "%I %p"):
                try:
                    parsed_time = datetime.strptime(raw_time, fmt)
                    return (0, parsed_time.hour * 60 + parsed_time.minute)
                except ValueError:
                    continue
            stamp = item.entry_timestamp or datetime.min
            stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
            return (1, stamp.timestamp())
        day_entries.sort(key=_entry_sort)

        # An opening/RI line and its first recorded act belong to one real entry
        # when they have the same displayed time. Fold all equal-time records
        # into one row so the export never repeats an entry time on separate rows.
        grouped = []
        for item in day_entries:
            display_time = _entry_time(item)
            key = display_time.upper().replace("HRS", "").strip()
            if grouped and key and grouped[-1]["key"] == key:
                grouped[-1]["items"].append(item)
            else:
                grouped.append({"key": key, "time": display_time, "items": [item]})

        def _group_actions(group):
            items = group["items"]
            return {
                "time": group["time"],
                "place": next((str((d.tech_artifacts_obtained or {}).get("place") or "").strip()
                               for d in items if isinstance(d.tech_artifacts_obtained, dict)
                               and (d.tech_artifacts_obtained or {}).get("place")), ps.upper()),
                "action_taken": " + ".join(dict.fromkeys(d.action_taken.strip() for d in items if d.action_taken and d.action_taken.strip())),
                "investigation_summary": "\n".join(d.investigation_summary.strip() for d in items if d.investigation_summary and d.investigation_summary.strip()),
            }

        opening_group = grouped[0] if grouped else {"time": "", "items": []}
        opening_items = opening_group["items"]
        if idx == 1:
            first_is_fir = bool(opening_items and isinstance(opening_items[0].tech_artifacts_obtained, dict)
                                and (opening_items[0].tech_artifacts_obtained.get("is_fir_initial_entry")
                                     or opening_items[0].tech_artifacts_obtained.get("fir_metadata")))
            first_syn = ("Opening + Perusal of FIR + Gist of the Case" if first_is_fir else
                         " + ".join(dict.fromkeys(d.action_taken.strip() for d in opening_items if d.action_taken and d.action_taken.strip())) or "Case registered")
            first_part = "\n".join(d.investigation_summary.strip() for d in opening_items if d.investigation_summary and d.investigation_summary.strip())
            if first_is_fir and fir_diary:
                # Keep Point 12 exactly as extracted, but precede it with the
                # standard opening particulars and a short contextual sentence.
                first_part = _fir_opening_narrative(fir_metadata, fir_diary.investigation_summary or "")
                other_opening_text = "\n".join(
                    d.investigation_summary.strip() for d in opening_items
                    if d.diary_id != fir_diary.diary_id and d.investigation_summary and d.investigation_summary.strip()
                )
                if other_opening_text:
                    first_part += "\n" + other_opening_text
            if not first_part:
                first_part = (f"Case registered on the basis of the written complaint of {case.complainant_name} "
                              f"dated {_fmt_date(case.complaint_date)} under {_fmt_sections(case.offense_sections or [])}. "
                              f"Took up investigation of the case.")
        else:
            previous_date = daily_groups[idx - 2][0]
            ri_text = (f"In this Case CD No -{int_to_roman(idx - 1)} dtd-{_fmt_date(previous_date)} "
                       f"duly submitted by me.\nBy this time resume further investigation of the case.")
            opening_action = _group_actions(opening_group) if opening_items else None
            first_syn = "RI" + (f" + {opening_action['action_taken']}" if opening_action and opening_action["action_taken"] else "")
            first_part = ri_text + (f"\n{opening_action['investigation_summary']}" if opening_action and opening_action["investigation_summary"] else "")
        actions = [_group_actions(group) for group in grouped[1:]]
        closing_time = grouped[-1]["time"] if grouped else ""
        if grouped and closing_time.upper().replace("HRS", "").strip() == grouped[-1]["key"]:
            # There is no separately captured closing time in the current entry
            # schema. Avoid printing the last action's time again as if it were
            # a distinct closing event.
            closing_time = ""
        out.append({
            "cd_number": int_to_roman(idx),
            "entry_date": _fmt_date(entry_date),
            "arrested": next((d.arrested_accused.strip() for d in reversed(day_entries) if d.arrested_accused and d.arrested_accused.strip()), "NIL"),
            "bailed": next((d.bailed_accused.strip() for d in reversed(day_entries) if d.bailed_accused and d.bailed_accused.strip()), "NIL"),
            "at_large": next((d.at_large_accused.strip() for d in reversed(day_entries) if d.at_large_accused and d.at_large_accused.strip()), ""),
            "t": opening_group["time"],
            "first_syn": first_syn,
            "first_part": first_part,
            "actions": actions,
            "closing_time": closing_time,
            "dsr_number": next((d.dsr_number for d in reversed(day_entries) if d.dsr_number), ""),
        })
    return {
        "ps": ps, "ps_upper": ps.upper(), "district_upper": district.upper(), "district": district, "io": io,
        "fir_no": case.fir_number, "fir_date": _fmt_date(case.complaint_date),
        "sections": _diary_sections(case.offense_sections),
        "complainant": case.complainant_name, "diaries": out,
    }


def _borders(table):
    pr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for e in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{e}")
        el.set(qn("w:val"), "single"); el.set(qn("w:sz"), "4"); el.set(qn("w:space"), "0"); el.set(qn("w:color"), "000000")
        b.append(el)
    pr.append(b)


def _cell(cell, text, bold=False, center=False, size=10.5):
    cell.text = ""
    lines = str(text).split("\n")
    para = cell.paragraphs[0]
    for i, line in enumerate(lines):
        if i:
            para = cell.add_paragraph()
        r = para.add_run(line)
        r.bold = bold
        r.font.size = Pt(size)
        r.font.name = "Times New Roman"
        para.paragraph_format.space_after = Pt(0)
        if center:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER


def build_docx(ctx: dict) -> bytes:
    doc = docx.Document()
    doc.styles["Normal"].font.name = "Times New Roman"
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Emu(7772400), Emu(10058400)
    sec.left_margin = sec.right_margin = Emu(548640)
    sec.top_margin = sec.bottom_margin = Emu(640080)
    usable = (7772400 - 2 * 548640)
    widths = [int(usable * f) for f in (0.14, 0.20, 0.24, 0.42)]

    for n, d in enumerate(ctx["diaries"]):
        action_count = len(d["actions"])
        t = doc.add_table(rows=11 + action_count, cols=4)
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _borders(t)

        def merged(r, a, b, text, **kw):
            c = t.cell(r, a).merge(t.cell(r, b))
            _cell(c, text, **kw)

        merged(0, 0, 3, "CASE DIARY UNDER SECTION 192 B.N.S.S\n(PRB Form No. 43 – Vide Rule 239)", bold=True, center=True, size=12)
        merged(1, 0, 1, ctx["ps_upper"], bold=True, center=True)
        merged(1, 2, 3, f"DISTRICT: {ctx['district_upper']}", bold=True, center=True)
        _cell(t.cell(2, 0), f"FIR No. {ctx['fir_no']}", bold=True)
        _cell(t.cell(2, 1), f"Date: {ctx['fir_date']}", bold=True)
        merged(2, 2, 3, f"Section- {ctx['sections']}", bold=True)
        merged(3, 0, 3, f"Name of the complainant: {ctx['complainant']}", bold=True)
        _cell(t.cell(4, 0), f"CD No: {d['cd_number']}", bold=True)
        merged(4, 1, 3, f"Date: {d['entry_date']}", bold=True)
        _cell(t.cell(5, 0), "Arrested and sent up", bold=True, center=True)
        _cell(t.cell(5, 1), "Released on bail", bold=True, center=True)
        merged(5, 2, 3, "At Large", bold=True, center=True)
        _cell(t.cell(6, 0), d["arrested"], center=True)
        _cell(t.cell(6, 1), d["bailed"], center=True)
        merged(6, 2, 3, d["at_large"], center=True)
        for i, h in enumerate(["Sl No. & hours of entry", "Place of entry", "Synopsis of entry", "PARTICULARS OF ENQUIRY"]):
            _cell(t.cell(7, i), h, bold=True, center=True)
        _cell(t.cell(8, 0), "I\n" + d["t"], center=True)
        _cell(t.cell(8, 1), ctx["ps_upper"], center=True)
        _cell(t.cell(8, 2), d["first_syn"])
        _cell(t.cell(8, 3), d["first_part"])
        for k, action in enumerate(d["actions"], start=1):
            row_idx = 8 + k
            _cell(t.cell(row_idx, 0), int_to_roman(k + 1) + "\n" + action["time"], center=True)
            _cell(t.cell(row_idx, 1), action["place"], center=True)
            _cell(t.cell(row_idx, 2), action["action_taken"])
            _cell(t.cell(row_idx, 3), action["investigation_summary"])
        closing_row = 9 + action_count
        _cell(t.cell(closing_row, 0), int_to_roman(action_count + 2) + "\n" + d["closing_time"], center=True)
        _cell(t.cell(closing_row, 1), ctx["ps_upper"], center=True)
        _cell(t.cell(closing_row, 2), "Closing")
        _cell(t.cell(closing_row, 3), f"At the side noted time closing the diary at {ctx['ps_upper']} pending further investigation.")
        dist_line = f"\n{ctx['district']} District Police" if ctx["district"] else ""
        signature_row = 10 + action_count
        merged(signature_row, 0, 3, f"Submitted\n\n\n..................................\n(Signature of the I.O.)\n{ctx['io']}\n{ctx['ps_upper']}{dist_line}")
        for row in t.rows:
            for i, w in enumerate(widths):
                if i < len(row.cells):
                    row.cells[i].width = Emu(w)
        if n < len(ctx["diaries"]) - 1:
            doc.add_page_break()

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@diary_export_router.get("/{case_id}/export-diary")
async def export_case_diary(
    case_id: uuid.UUID,
    format: Literal["pdf", "docx"] = Query("docx", description="Export format: docx or pdf"),
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Official PRB Form 43 Case Diary generated from the database (one page per diary)."""
    owner_id = extract_owner_id(user)
    stmt = select(Case).where(Case.case_id == case_id)
    if owner_id:
        stmt = stmt.where(Case.owner_id == owner_id)
    case_obj = (await db.execute(stmt)).scalar_one_or_none()
    if not case_obj:
        raise HTTPException(status_code=404, detail="Case not found or access denied")

    if not case_obj.io_name and user.get("name"):
        case_obj.io_name = user.get("name")
    if not case_obj.police_station and user.get("station"):
        case_obj.police_station = user.get("station")

    diaries = (await db.execute(
        select(CaseDiary).where(CaseDiary.case_id == case_id).order_by(CaseDiary.entry_date.asc(), CaseDiary.entry_timestamp.asc())
    )).scalars().all()
    evidences = (await db.execute(select(CaseEvidence).where(CaseEvidence.case_id == case_id))).scalars().all()
    if not diaries:
        raise HTTPException(status_code=400, detail="No Case Diary records found for this case.")

    ctx = build_context(case_obj, diaries, evidences)
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(case_obj.fir_number))

    if format == "pdf":
        from weasyprint import HTML
        env = Environment(loader=FileSystemLoader("templates/"), autoescape=True)
        html = env.get_template("case_diary_template.html").render(ctx=ctx)
        return Response(HTML(string=html).write_pdf(), media_type="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename=Case_Diary_FIR_{safe}.pdf"})

    return Response(
        build_docx(ctx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=Case_Diary_FIR_{safe}.docx"},
    )
