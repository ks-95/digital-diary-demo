# src/models/models.py
import uuid
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import String, Text, Boolean, Date, DateTime, ForeignKey, ARRAY, BigInteger
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from utils.db import Base

class Case(Base):
    __tablename__ = "cases"

    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    crime_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    fir_number: Mapped[str] = mapped_column(String(50), nullable=False)
    police_station: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    district: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    io_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    complaint_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    complainant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    complainant_father: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    complainant_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    complainant_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    offense_sections: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False)
    stolen_property_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    complaint_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    case_status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    investigation_domain: Mapped[str] = mapped_column(String(20), default="UNCLASSIFIED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    diaries: Mapped[List["CaseDiary"]] = relationship("CaseDiary", back_populates="case", cascade="all, delete-orphan", order_by="CaseDiary.entry_timestamp.asc()")
    evidence: Mapped[List["CaseEvidence"]] = relationship("CaseEvidence", back_populates="case", cascade="all, delete-orphan")

class CaseDiary(Base):
    __tablename__ = "case_diaries"

    diary_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    entry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    diary_entry_time: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    investigation_summary: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    tech_artifacts_obtained: Mapped[dict] = mapped_column(JSONB, default=dict)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    moe_file_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dsr_number: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    arrested_accused: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bailed_accused: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    at_large_accused: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    case: Mapped["Case"] = relationship("Case", back_populates="diaries")

class CaseEvidence(Base):
    __tablename__ = "case_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    record_category: Mapped[str] = mapped_column(String(30), default="EVIDENCE", nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    extracted_details: Mapped[dict] = mapped_column(JSONB, default=dict)
    file_path: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    case: Mapped["Case"] = relationship("Case", back_populates="evidence")

class CaseDocumentChunk(Base):
    __tablename__ = "case_document_chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cases.case_id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("case_evidence.evidence_id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)


class UserSubscription(Base):
    __tablename__ = "user_subscriptions"

    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(30), default="razorpay", nullable=False)
    provider_subscription_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    plan_id: Mapped[str] = mapped_column(String(100), nullable=False)
    checkout_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created", nullable=False, index=True)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    provider_subscription_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
