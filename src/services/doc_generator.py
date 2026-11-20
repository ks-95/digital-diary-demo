# src/services/doc_generator.py
"""Chargesheet / Final Report generator – W.B.P Form No. 39 (Section 193 BNSS).

Layout mirrors the department's sample (Charge_sheet-_10-25.docx):
legal page (8.5 x 14 in), Times New Roman 11 pt, items 1-17 in the same order and wording,
the property table (item 11), the witness table (item 14), the 17-item accused block (item 12),
and the "Continuation of Column 17" pages.
Values that are not known stay blank / N.A. – nothing is invented.
"""
import os
import re
from datetime import date, datetime
from typing import Dict, List

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Pt

from schemas.dtos import ChargesheetStructuredData, CSAccused

FONT = "Times New Roman"
ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii", "xiii", "xiv", "xv", "xvi", "xvii"]
DOTS = "………………"


# ───────────────────────────── helpers ─────────────────────────────
def _fmt_date(v) -> str:
    if not v:
        return ""
    if isinstance(v, (date, datetime)):
        return v.strftime("%d.%m.%Y")
    s = str(v).strip()
    for f in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, f).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return s


def split_sections(sections) -> Dict[str, List[str]]:
    """Normalize and group section references by Act without repeating act titles."""
    groups: Dict[str, List[str]] = {"BNS": [], "IT Act": [], "IPC": [], "Other": []}
    section_pattern = re.compile(r"(?<![A-Za-z0-9])\d+[A-Za-z]?(?:\(\d+[A-Za-z]?\))*")
    act_patterns = (
        ("IT Act", re.compile(r"\b(?:it\s*act|information\s+technology\s+act)\b", re.I)),
        ("BNS", re.compile(r"\b(?:bns|b\.?n\.?s\.?|bharatiya\s+nyaya\s+sanhita)\b", re.I)),
        ("IPC", re.compile(r"\b(?:ipc|i\.?p\.?c\.?|indian\s+penal\s+code)\b", re.I)),
    )
    raw_sections = [sections] if isinstance(sections, str) else (sections or [])
    for raw in raw_sections:
        t = str(raw).strip()
        if not t:
            continue
        # Collapse OCR/model variants such as "Bharatiya Nyaya Sanhita (), 2023".
        cleaned = re.sub(r"\(\s*\)", "", t)
        act_markers = sorted((match.start(), name) for name, pattern in act_patterns for match in pattern.finditer(cleaned))
        section_matches = list(section_pattern.finditer(cleaned))
        canonical = []
        for match in section_matches:
            number = match.group(0).strip()
            if number.isdigit() and 1800 <= int(number) <= 2100:
                continue  # Act publication years are not section numbers.
            if not number:
                continue
            preceding = [marker for marker in act_markers if marker[0] < match.start()]
            following = [marker for marker in act_markers if marker[0] >= match.end()]
            act = preceding[-1][1] if preceding else (following[0][1] if following else None)
            if not act:
                if number not in canonical:
                    canonical.append(number)
            elif number not in groups[act]:
                groups[act].append(number)
        if not act_markers:
            # Keep non-standard Acts in their source wording, but remove empty
            # legal-name parentheses and repeated whitespace.
            other = re.sub(r"\s+", " ", cleaned).strip(" ,;.-")
            if other and other not in groups["Other"]:
                groups["Other"].append(other)
        elif canonical:
            groups["Other"].extend(n for n in canonical if n not in groups["Other"])
    return groups


def _fmt_sections(sections: List[str]) -> str:
    """Render grouped references, e.g. '318(4)/319(2) BNS, 66D IT Act'."""
    g = split_sections(sections)
    parts = []
    if g["BNS"]:
        parts.append("/".join(g["BNS"]) + " BNS")
    if g["IPC"]:
        parts.append("/".join(g["IPC"]) + " IPC")
    if g["IT Act"]:
        parts.append("/".join(g["IT Act"]) + " IT Act")
    if g["Other"]:
        parts.extend(g["Other"])
    return ", ".join(parts)


def _set_cell_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "000000")
        borders.append(el)
    tblPr.append(borders)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


class _Doc:
    def __init__(self):
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = FONT
        st.font.size = Pt(11)
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        st.paragraph_format.space_after = Pt(0)
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Emu(7772400), Emu(12801600)      # 8.5 x 14 in (legal)
        sec.left_margin, sec.right_margin = Emu(347345), Emu(342900)
        sec.top_margin, sec.bottom_margin = Emu(402590), Emu(720090)

    def p(self, text="", bold=False, align=None, size=None, indent=None, justify=False, space_after=0):
        para = self.doc.add_paragraph()
        if text:
            r = para.add_run(text)
            r.bold = bold
            r.font.name = FONT
            if size:
                r.font.size = Pt(size)
        if justify:
            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        if align == "center":
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if indent:
            para.paragraph_format.left_indent = Pt(indent)
        para.paragraph_format.space_after = Pt(space_after)
        return para

    def table(self, headers: List[str], widths_cm: List[float], numbered: bool):
        t = self.doc.add_table(rows=1, cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _set_cell_borders(t)
        for i, h in enumerate(headers):
            c = t.rows[0].cells[i]
            c.text = ""
            r = c.paragraphs[0].add_run(h)
            r.bold = True
            r.font.size = Pt(10)
        _repeat_header(t.rows[0])
        if numbered:
            cells = t.add_row().cells
            for i in range(len(headers)):
                cells[i].text = str(i + 1)
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        for row in t.rows:
            for i, w in enumerate(widths_cm):
                row.cells[i].width = Emu(int(w * 360000))
        return t

    def row(self, t, values: List[str], widths_cm: List[float]):
        cells = t.add_row().cells
        for i, v in enumerate(values):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v or ""))
            r.font.size = Pt(10)
            cells[i].width = Emu(int(widths_cm[i] * 360000))

    def page_break(self):
        self.doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


# ───────────────────────────── main builder ─────────────────────────────
def _accused_block(d: _Doc, idx: int, a: CSAccused):
    letter = f"({chr(65 + idx)})"
    pad = "           "
    d.p(f"{pad}{letter}    (i)     Name…………………: {a.name}", bold=True)
    rows = [
        ("(ii)", "Father’s/ Husband’s Name: -:", a.father_name),
        ("(iii)", "Date/ Year of Birth………", a.age_or_dob),
        ("(iv)", "Sex…………………", a.sex),
        ("(v)", "Nationality…………", a.nationality),
        ("(vi)", "Religion……………", a.religion),
        ("(vii)", "Whether SC/ST………………", a.sc_st),
        ("(viii)", "Occupation……………………", a.occupation),
    ]
    for no, label, val in rows:
        d.p(f"{pad}      {no}   {label} {val}".rstrip())
    d.p(f"{pad}      (ix) Address: {a.address}", justify=True)
    d.p(f"{pad}      (x)    Provisional Criminal No…………N.A.…………", justify=True)
    d.p(f"{pad}      (xi)   Regular criminal No…………N.A.…………")
    d.p(f"{pad}      (xii)  Date of Arrest: {_fmt_date(a.date_of_arrest)}")
    d.p(f"{pad}      (xiii) Date of Released on Bail: {_fmt_date(a.date_released_on_bail)}")
    d.p(f"{pad}      (xiv) Date on which forwarded to Court– {_fmt_date(a.date_forwarded_to_court)}")
    d.p(f"{pad}      (xv)  Under Act and section: {_fmt_sections(a.sections)}")
    d.p(f"{pad}      (xvi) Name(s) and Address (es) of sureties…{a.sureties or 'N. A'}…………")
    d.p(f"{pad}      (xvii) Previous conviction with case reference…{a.previous_conviction or 'N. A'}…………")
    d.p(f"{pad}      (xviii) Custody / forwarding status:")
    d.p(f"{pad}      Proclaimed offender: {a.custody_status}")


def build_chargesheet_docx(case_data: dict, ai_report: ChargesheetStructuredData, output_dir: str = "generated_docs") -> str:
    os.makedirs(output_dir, exist_ok=True)
    d = _Doc()
    ai = ai_report

    district = case_data.get("district") or ""
    ps = case_data.get("police_station") or ""
    fir_no = case_data.get("fir_number") or ""
    fir_date = _fmt_date(case_data.get("complaint_date"))
    year = fir_date[-4:] if len(fir_date) >= 4 else str(date.today().year)
    cs_no = case_data.get("cs_number") or "……"
    cs_date = _fmt_date(case_data.get("cs_date") or date.today())
    io_name = case_data.get("io_name") or ""
    io_rank = case_data.get("io_rank") or "………………"
    sections = case_data.get("offense_sections") or []
    groups = split_sections(sections)
    bns_txt = "/".join(groups["BNS"])
    it_txt = "/".join(groups["IT Act"])
    ipc_txt = "/".join(groups["IPC"])
    other_txt = "; ".join(groups["Other"]) or "N.A."

    # ── Heading ─────────────────────────────────────────────────────────
    d.p("W.B.P Form No. 39           CHARGE SHEET/ FINAL REPORT", align="center")
    d.p("(Under section 193 B.N.S.S)    ", bold=True)
    d.p(f" IN THE COURT OF Ld. CJM, {district}.")
    d.p(f"1. Dist-. {district}…….. P.S- {ps}…Year…{year}...FIR No…{fir_no}…Date:{fir_date}")
    d.p(f"2.      Final Report/Charge sheet No: -{cs_no}……………… 3. Date: {cs_date}")
    d.p("4. Acts and Sections:")
    act_lines = []
    if bns_txt:
        act_lines.append(("(i)", "B.N.S.", f"{bns_txt} BNS"))
    if it_txt:
        act_lines.append(("(ii)", "Information Technology Act", f"{it_txt} IT Act"))
    if ipc_txt:
        act_lines.append(("(iii)", "I.P.C.", f"{ipc_txt} IPC"))
    for marker, act, section_text in act_lines:
        d.p(f"       {marker} Act: {act}; Section: {section_text}")
    d.p(f"       (iv) Other Acts and Sections: {other_txt}.")
    d.p(f"5.    Type of final report: Charge Sheet/ untraced/ Un-occurred/ not Charge Sheeted for want of evidence ({ai.final_report_type or 'Charge Sheeted'})")
    d.p("6.    If F.R un-occurred: False/ Mistake of Fact/ Mistake of Law/ Non cognizable/ Civil Nature…NA…")
    d.p(f"7.    If Supplementary of Original: {ai.original_or_supplementary or 'Original'}.")
    d.p(f"8.    Name, Rank and Number (if any) of the I.O.(s): {io_name}")
    d.p(f"9. (a) Name of Complainant / Informant: {case_data.get('complainant_name') or ''}")
    d.p(f"    (b)  Father’s /Husband’s Name: {case_data.get('complainant_father') or ''}")
    d.p(f"10.  Date on which the complainant /Informant was informed of the result…. On {_fmt_date(ai.complainant_informed_date)}")
    d.p("11.  Detail of properties/Articles/Document recovered/ Seized during investigation and relied upon (separate list can")
    d.p("Be attached, if necessary): -------")

    widths = [1.2, 5.2, 2.0, 2.2, 6.4, 2.0]
    t = d.table(["SL No", "Property Description", "Estimated Value\n(In RS)", "PS Property Regd\nNo.",
                 "From whom/where recovered or seized", "Disposal"], widths, numbered=True)
    for i, s in enumerate(ai.seizures, 1):
        d.row(t, [i, s.description, s.estimated_value or "NA", s.pr_no, s.seized_from, s.disposal], widths)

    n = len(ai.accused)
    words = {1: "One (01)", 2: "Two (02)", 3: "Three (03)", 4: "Four (04)", 5: "Five (05)"}
    d.p(f"11. A.  Number of accused persons charge sheeted: {words.get(n, f'{n:02d}')}" if n else "11. A.  Number of accused persons charge sheeted: Nil")
    d.p("11. B.  Number of accused persons not charge sheeted. N.A.")
    d.p("12.   Particulars of accused persons charge sheeted.")
    for i, a in enumerate(ai.accused):
        _accused_block(d, i, a)

    d.p("13.     Particulars of accused persons not charge sheeted:NIL UNDER ALL HEADS.")
    for line in ["(i)     Name:…………………….", "(ii)    Father’s/ Husband’s Name:", "(iii)   Date/ Year of Birth………..",
                 "(iv)   Sex………………...", "(v)    Nationality…………….", "(vi)   Religion………………", "(vii)  Whether SC/ST…………",
                 "(viii) Occupation…………….", "(ix)   Address: ………………..…", "(x)    Provisional Criminal No: …",
                 "(xi)   Suspicion Approved:",
                 "(xii)   Forwarded /Bailed by Police/ Bailed by Court/In judicial Custody/ Absconding/Proclaimed offender: ",
                 "(xiii)  Under Act and Sections: ", "(xiv)  Any special remarks including reason for not charge sheeted:"]:
        d.p("           " + line)

    d.p("14.     Particulars of witnesses to be examined")
    w2 = [1.2, 4.2, 3.0, 2.0, 2.2, 4.8, 3.6]
    t2 = d.table(["SL No", "Name", "Father/Husbands Name", "Date/Year/Birth", "Occupation", "Address",
                  "Type of evidence to be tendered"], w2, numbered=False)
    for i, w in enumerate(ai.witnesses, 1):
        d.row(t2, [i, w.name, w.father_name, w.age_or_dob, w.occupation, w.address, w.evidence_type], w2)
    d.p("(All may kindly be summoned during trial.)", bold=True, align="center")
    d.p("15.    If F.R. is false, indicate action taken proposed to be taken u/s 182/211 IPC. – N.A.")
    d.p(f"16.    Result of laboratory analysis: {ai.lab_result or 'N.A.'}")

    # ── 17. Brief fact ──────────────────────────────────────────────────
    d.p("17.  Brief fact of this case: -", justify=True)
    for para in ai.brief_facts:
        d.p(para, justify=True, space_after=6)
    for sec in ai.investigation_sections:
        d.p(sec.heading, bold=True, justify=True)
        for pt in sec.points:
            d.p(pt, justify=True, space_after=3)

    def signature():
        d.p(f"Date of submission: {cs_date}")
        d.p("Signature of the investigating Officer")
        d.p("Submitting the Final Report/Charge Sheet")
        d.p(f"Name: {io_name.upper()}")
        d.p(f"Rank: {io_rank}")
        d.p(f"{ps}", align="center")
        d.p(f"Date: {cs_date}")

    signature()

    # ── Continuation of Column 17 ───────────────────────────────────────
    d.page_break()
    d.p("Continuation of Column Number .17(Brief fact of this case)", bold=True)
    for sec in ai.continuation_sections:
        d.p(sec.heading, bold=True, justify=True)
        for pt in sec.points:
            d.p(pt, justify=True, space_after=3)

    d.p("Evidences against specific individual accused persons with the sections of charges proved against them.", bold=True, justify=True)
    for a in ai.accused:
        addr = f", {a.address}" if a.address else ""
        age = f" ({a.age_or_dob})" if a.age_or_dob else ""
        father = f", S/o {a.father_name}" if a.father_name else ""
        d.p(f"Accused details: {a.name}{age}{father}{addr}", bold=True, justify=True)
        d.p(f"Charges - {_fmt_sections(a.sections)}.", bold=True, justify=True)
        if a.documentary_evidence:
            d.p("Documentary evidence against the accused: ", bold=True, justify=True)
            for x in a.documentary_evidence:
                d.p(x, justify=True, space_after=3)
        if a.material_evidence:
            d.p("Material (Digital & documentary) evidence which are seized from the accused:", bold=True, justify=True)
            for x in a.material_evidence:
                d.p(x, justify=True, space_after=3)
        if a.prosecution_witnesses:
            d.p("Prosecution witnesses which prove the charges of the accused:", bold=True, justify=True)
            for x in a.prosecution_witnesses:
                d.p(x, justify=True, space_after=3)

    if ai.concluding_opinion:
        d.p(ai.concluding_opinion, bold=True, justify=True, space_after=6)
    d.p("The witnesses noted in column No 14 are the main evidence of the case and may kindly be summoned during the trial, as they will prove the facts.")
    d.p(f"Date of submission: {cs_date}", justify=True)
    d.p("Signature of the investigating Officer")
    d.p("Submitting the Final Report/Charge Sheet")
    d.p(f"Name: {io_name.upper()}")
    d.p(f"Rank: {io_rank}")
    d.p(f"           {ps}", align="center")
    d.p(f"Date: {cs_date}")

    clean = re.sub(r'[\\/*?:"<>|]', "_", str(case_data.get("crime_number") or fir_no or "case"))
    path = os.path.join(output_dir, f"Chargesheet_{clean}.docx")
    d.doc.save(path)
    return path
