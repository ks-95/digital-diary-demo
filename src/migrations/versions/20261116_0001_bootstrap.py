"""Bootstrap the current schema and adopt existing local installations.

Revision ID: 20261116_0001
Revises:
Create Date: 2026-11-16
"""
from alembic import op

revision = "20261116_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # This baseline is intentionally idempotent: it creates tables for a new
    # Supabase project and adds columns missing from older app databases.
    from utils.db import Base
    import models.models  # noqa: F401
    import models.user  # noqa: F401

    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    statements = (
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS complaint_date DATE",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS complainant_address TEXT",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS stolen_property_value VARCHAR(100)",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS complaint_summary TEXT",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS police_station VARCHAR(150)",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS district VARCHAR(100)",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS io_name VARCHAR(150)",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS complainant_father VARCHAR(150)",
        "ALTER TABLE cases ADD COLUMN IF NOT EXISTS investigation_domain VARCHAR(20) NOT NULL DEFAULT 'UNCLASSIFIED'",
        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS record_category VARCHAR(30) NOT NULL DEFAULT 'EVIDENCE'",
        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS title VARCHAR(255)",
        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255)",
        "ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS extracted_details JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS moe_file_path VARCHAR(255)",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS dsr_number VARCHAR(50)",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS arrested_accused TEXT",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS bailed_accused TEXT",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS at_large_accused TEXT",
        "ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS diary_entry_time VARCHAR(20)",
        "UPDATE case_evidence SET record_category = 'CASE_DOCUMENT' WHERE record_category = 'EVIDENCE' AND artifact_type IN ('SEIZURE_LIST', 'CC_CERTIFICATE', 'COURT_CUSTODY_PRAYER', 'COURT_ORDER', 'MALKHANA_REGISTER_CMR', 'CASE_DIARY', 'STATEMENT', 'NOTICE_OR_REQUISITION', 'REPORT')",
    )
    for statement in statements:
        op.execute(statement)


def downgrade():
    # This adoption/bootstrap migration must not drop operational case data.
    pass
