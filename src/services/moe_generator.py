"""Memo of Evidence (MoE) generator – follows the department MoE template headings.

MoE is only produced when the case has a DSR number.
"""
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUT_DIR = Path(__file__).resolve().parents[1] / "generated_docs"


def _bold(doc, label: str, value: str = ""):
    p = doc.add_paragraph()
    r = p.add_run(label)
    r.bold = True
    if value:
        p.add_run(" " + value)
    return p


def build_moe_docx(case: dict, diaries: list, dsr_number: str) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)

    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hr = h.add_run("MEMO OF EVIDENCE")
    hr.bold = True
    hr.underline = True
    hr.font.size = Pt(14)

    ps = case.get("police_station") or ""
    district = case.get("district") or ""
    io = case.get("io_name") or ""
    if district:
        ps = f"{ps}, {district}".strip(", ")
    sections = ", ".join(case.get("offense_sections") or [])
    cdate = case.get("complaint_date") or ""
    victim = f"{case.get('complainant_name', '')}, {case.get('complainant_address') or ''}".strip(", ")

    _bold(doc, "DSR No.: -", dsr_number)
    _bold(doc, "PS Case No.", f"{ps} Case No. – {case.get('fir_number', '')}, dt. – {cdate}, U/S- {sections}")
    _bold(doc, "Name, Age & Address of Victim:", victim)
    _bold(doc, "P.O & D.O:", "")
    _bold(doc, "Complainant: -", victim)
    _bold(doc, "Name of I.O.:-", io)
    _bold(doc, "Gist of the Case:-", case.get("complaint_summary") or "")
    _bold(doc, "Motive: -", "The accused committed the offence for wrongful monetary gain.")

    _bold(doc, "Name & address of the accused with date of Arrest / Surrender: -")
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    for i, c in enumerate(["SL No", "Name, Parentage and Age", "Address", "Date of Arrest / Surrender in Case", "FIR named/ others"]):
        t.rows[0].cells[i].text = c

    _bold(doc, "Other Evidence: -")
    _bold(doc, "Seizure list with date:")
    t = doc.add_table(rows=1, cols=6)
    t.style = "Table Grid"
    for i, c in enumerate(["Sl No", "Description of Seizure Property", "Labeling Done (Y/N)", "Date of Seizure", "From whom seized", "PR No"]):
        t.rows[0].cells[i].text = c

    _bold(doc, "(11) Injury report/PM Report/Medical Exam. Report Victim collected :-", "N.A")
    _bold(doc, "(12) Details of Inquest / PM :-", "N.A")
    _bold(doc, "(13) Details of injury report/ Medical Examination report:", "N.A")
    _bold(doc, "(14) Details of FSL Report/ Expert opinion: -", "Yet to be received.")
    _bold(doc, "(15) Total No. of photograph of PO/ Deceased taken & enclosed in CD :-", "NA")
    _bold(doc, "(16) Person examined & statement recorded U/S 180 B.N.S.S.: -")
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    for i, c in enumerate(["Sl. No.", "Name, Parentage & Address of person examined", "Relation with Victim", "Date of Examination", "Type of Witness"]):
        t.rows[0].cells[i].text = c

    _bold(doc, "(17) Evidence chart: -")
    _bold(doc, "Points to be proved by the prosecution (including role of individual accused / Recorded articles).")
    _bold(doc, "Evidence to be proved each point / Nature of Testimony (Name of witness / document / seizure etc.)")

    _bold(doc, "(18) Opinion and Prayer of I.O.")
    for d in diaries:
        doc.add_paragraph(f"{d.get('entry_date')}: {d.get('investigation_summary')}")
    doc.add_paragraph("Submitted").alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _bold(doc, "(19) Opinion of Dy. SP (D & T):-")
    _bold(doc, "(20) Opinion of Addl. S.P. (Ops):")
    _bold(doc, "(21) Final Order:-")

    safe = re.sub(r'[\\/*?:"<>|]', "_", dsr_number)
    path = OUT_DIR / f"MoE_DSR_{safe}.docx"
    doc.save(str(path))
    return str(path)
