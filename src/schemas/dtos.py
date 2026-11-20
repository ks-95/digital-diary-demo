from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Optional, Dict, Any
from datetime import date, datetime
import uuid


class CaseCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    crime_number: str = Field(..., example="CY/2026/0142")
    fir_number: str = Field(..., example="FIR-89/2026")
    police_station: Optional[str] = Field(None, example="Cyber Crime PS, Jhargram")
    district: Optional[str] = Field(None, example="Jhargram")
    io_name: Optional[str] = Field(None, example="Inspector Rabi Swarnakar")
    complainant_father: Optional[str] = Field(None, example="Late Subal Chandra Murmu")
    complainant_name: str = Field(..., example="Ramesh Kumar")
    complainant_phone: Optional[str] = Field(None, example="+919876543210")
    offense_sections: List[str] = Field(default_factory=list, example=["Sec 318(4) BNS"])
    complaint_date: Optional[date] = Field(None, example="2026-10-25")
    complainant_address: Optional[str] = Field(None, example="123 Park Street, Kolkata")
    stolen_property_value: Optional[str] = Field(None, example="Rs. 19,72,159")
    complaint_summary: Optional[str] = Field(None, example="Victim lost money via UPI fraud.")
    dsr_number: Optional[str] = Field(None, description="DSR number – required when MoE is attached")
    initial_diary_summary: Optional[str] = None
    initial_action_taken: Optional[str] = None
    tech_artifacts: Optional[Dict[str, Any]] = None
    investigation_domain: str = Field("UNCLASSIFIED", description="CYBER, NON_CYBER, or UNCLASSIFIED")

    @field_validator("complaint_date", mode="before")
    @classmethod
    def parse_complaint_date(cls, v):
        if not v or v in ("", "null", "N/A", "None"):
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.strip()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%Y/%m/%d"):
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    pass
        return None

    @field_validator("offense_sections", mode="before")
    @classmethod
    def parse_offense_sections(cls, v):
        if not v:
            return []
        if isinstance(v, str):
            parts = [s.strip() for s in v.replace(";", ",").split(",") if s.strip()]
            return parts
        if isinstance(v, list):
            clean_list = [str(item).strip() for item in v if str(item).strip()]
            return clean_list
        return []


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    case_id: uuid.UUID
    crime_number: str
    fir_number: str
    police_station: Optional[str] = None
    district: Optional[str] = None
    io_name: Optional[str] = None
    complainant_father: Optional[str] = None
    complainant_name: str
    complainant_phone: Optional[str] = None
    complainant_address: Optional[str] = None
    offense_sections: List[str]
    complaint_date: Optional[date] = None
    stolen_property_value: Optional[str] = None
    complaint_summary: Optional[str] = None
    case_status: str
    investigation_domain: str = "UNCLASSIFIED"
    created_at: datetime


class DiaryCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    entry_date: Optional[date] = Field(default_factory=date.today)
    diary_entry_time: Optional[str] = Field(None, description="Officer-recorded local time, HH:mm")
    investigation_summary: str = Field(..., example="Interrogated suspect regarding UPI transactions.")
    action_taken: str = Field(..., example="Notice u/s 94 BNSS issued to Axis Bank.")
    tech_artifacts_obtained: Optional[Dict[str, Any]] = Field(default_factory=dict)
    dsr_number: Optional[str] = Field(None, description="DSR number for MoE attachment")
    arrested_accused: Optional[str] = Field(None, description="Arrested and sent up (names)")
    bailed_accused: Optional[str] = Field(None, description="Released on bail (names)")
    at_large_accused: Optional[str] = Field(None, description="At large (names)")

    @field_validator("entry_date", mode="before")
    @classmethod
    def parse_entry_date(cls, v):
        if not v or v in ("", "null", "N/A", "None"):
            return date.today()
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.strip()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
                try:
                    return datetime.strptime(v, fmt).date()
                except ValueError:
                    pass
        return date.today()


class DiaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    diary_id: uuid.UUID
    case_id: uuid.UUID
    entry_date: date
    diary_entry_time: Optional[str] = None
    investigation_summary: str
    action_taken: str
    tech_artifacts_obtained: Optional[Dict[str, Any]] = None
    entry_timestamp: datetime
    entry_hash: str
    is_locked: bool
    moe_file_path: Optional[str] = None
    dsr_number: Optional[str] = None
    arrested_accused: Optional[str] = None
    bailed_accused: Optional[str] = None
    at_large_accused: Optional[str] = None


# ── Chargesheet (W.B.P Form No. 39) structured data ──────────────────────────
# Every field has a default so a partially-filled AI answer never breaks document generation.
# Rule: unknown values stay "" / "N.A." – the AI must never invent facts.
class CSAccused(BaseModel):
    name: str = ""
    father_name: str = ""
    age_or_dob: str = ""
    sex: str = ""
    nationality: str = ""
    religion: str = ""
    sc_st: str = ""
    occupation: str = ""
    address: str = ""
    date_of_arrest: str = ""
    date_released_on_bail: str = ""
    date_forwarded_to_court: str = ""
    sections: List[str] = Field(default_factory=list)
    sureties: str = ""
    previous_conviction: str = ""
    custody_status: str = ""
    documentary_evidence: List[str] = Field(default_factory=list)
    material_evidence: List[str] = Field(default_factory=list)
    prosecution_witnesses: List[str] = Field(default_factory=list)


class CSWitness(BaseModel):
    name: str = ""
    father_name: str = ""
    age_or_dob: str = ""
    occupation: str = ""
    address: str = ""
    evidence_type: str = "Witness"


class CSSeizure(BaseModel):
    description: str = ""
    estimated_value: str = ""
    pr_no: str = ""
    seized_from: str = ""
    disposal: str = ""


class CSSection(BaseModel):
    heading: str = ""
    points: List[str] = Field(default_factory=list)


class ChargesheetStructuredData(BaseModel):
    final_report_type: str = "Charge Sheet"
    original_or_supplementary: str = "Original"
    complainant_informed_date: str = ""
    seizures: List[CSSeizure] = Field(default_factory=list)
    accused: List[CSAccused] = Field(default_factory=list)
    witnesses: List[CSWitness] = Field(default_factory=list)
    lab_result: str = ""
    brief_facts: List[str] = Field(default_factory=list)
    investigation_sections: List[CSSection] = Field(default_factory=list)
    continuation_sections: List[CSSection] = Field(default_factory=list)
    concluding_opinion: str = ""


# ── Auth Schemas ──────────────────────────────────────────────
class RegisterRequest(BaseModel):
    mobile_number: str = Field(..., example="9876543210")
    password: str = Field(..., min_length=6, max_length=64, example="secret123")
    name: Optional[str] = Field(None, example="Officer Ramesh")
    station: Optional[str] = Field(None, example="Cyber Crime PS Kolkata")

    @field_validator("mobile_number")
    @classmethod
    def _valid_mobile(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if len(digits) != 10 or digits[0] not in "6789":
            raise ValueError("Enter a valid 10-digit Indian mobile number.")
        return digits


class LoginRequest(BaseModel):
    mobile_number: str
    password: str

    @field_validator("mobile_number")
    @classmethod
    def _norm_mobile(cls, v: str) -> str:
        digits = "".join(ch for ch in v if ch.isdigit())
        return digits[2:] if len(digits) == 12 and digits.startswith("91") else digits


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    mobile_number: str
    name: Optional[str] = None
    station: Optional[str] = None
