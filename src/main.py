import asyncio
import os
from contextlib import asynccontextmanager


# Point WeasyPrint to the MSYS2 UCRT64 binary directory where libgobject-2.0-0.dll lives
MSYS2_BIN = r"C:\msys64\ucrt64\bin"
if os.path.exists(MSYS2_BIN):
    if hasattr(os, 'add_dll_directory'):
        os.add_dll_directory(MSYS2_BIN)
    os.environ["PATH"] = MSYS2_BIN + os.pathsep + os.environ.get("PATH", "")
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from fastapi import HTTPException, status

from utils.settings import settings
from utils.security import get_current_user
from utils.db import Base, engine
import models.models  # Ensures all SQLAlchemy models are registered on Base.metadata
import models.user    # Ensures User model is registered on Base.metadata
from routers.cases import case_routes
from routers.chargesheet import chargesheet_router
from routers.diaries import diaries_router
from routers.ai_case_scan import case_routes_ai
from routers.case_diary_export import diary_export_router
from routers.auth import auth_router
from routers.moe import moe_router
from routers.billing import billing_router, require_active_subscription
from services.ai_provider import close_ai_provider_clients


async def _init_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Safe migration if table already exists without newer columns
        try:
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS complaint_date DATE;"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS complainant_address TEXT;"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS stolen_property_value VARCHAR(100);"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS complaint_summary TEXT;"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS police_station VARCHAR(150);"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS district VARCHAR(100);"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS io_name VARCHAR(150);"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS complainant_father VARCHAR(150);"))
            await conn.execute(text("ALTER TABLE cases ADD COLUMN IF NOT EXISTS investigation_domain VARCHAR(20) NOT NULL DEFAULT 'UNCLASSIFIED';"))
            await conn.execute(text("ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS record_category VARCHAR(30) NOT NULL DEFAULT 'EVIDENCE';"))
            await conn.execute(text("UPDATE case_evidence SET record_category = 'CASE_DOCUMENT' WHERE record_category = 'EVIDENCE' AND artifact_type IN ('SEIZURE_LIST', 'CC_CERTIFICATE', 'COURT_CUSTODY_PRAYER', 'COURT_ORDER', 'MALKHANA_REGISTER_CMR', 'CASE_DIARY', 'STATEMENT', 'NOTICE_OR_REQUISITION', 'REPORT');"))
            await conn.execute(text("ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS title VARCHAR(255);"))
            await conn.execute(text("ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS original_filename VARCHAR(255);"))
            await conn.execute(text("ALTER TABLE case_evidence ADD COLUMN IF NOT EXISTS extracted_details JSONB NOT NULL DEFAULT '{}'::jsonb;"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS moe_file_path VARCHAR(255);"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS dsr_number VARCHAR(50);"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS arrested_accused TEXT;"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS bailed_accused TEXT;"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS at_large_accused TEXT;"))
            await conn.execute(text("ALTER TABLE case_diaries ADD COLUMN IF NOT EXISTS diary_entry_time VARCHAR(20);"))
        except Exception as exc:
            print(f"[Startup Notice] Database compatibility migration failed: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Production schema changes are applied explicitly with Alembic before the
    # API starts. Development can retain the convenient create/compat path.
    if settings.ENVIRONMENT.lower() == "production":
        if settings.AUTO_INIT_DB:
            raise RuntimeError("Set AUTO_INIT_DB=false in production and run Alembic migrations before startup.")
        if not settings.DB_SSL:
            raise RuntimeError("DB_SSL=true is required for production database connections.")
        if len(settings.JWT_SECRET_KEY) < 32:
            raise RuntimeError("Set a random JWT_SECRET_KEY with at least 32 characters before production startup.")
        cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
        if not cors_origins or "*" in cors_origins:
            raise RuntimeError("Wildcard CORS origins are not allowed in production; list the web app origin.")
        if settings.STORAGE_BACKEND.lower() != "supabase":
            raise RuntimeError("Production requires STORAGE_BACKEND=supabase so case files use persistent private storage.")
        if not (settings.SUPABASE_URL and (settings.SUPABASE_SECRET_KEY or settings.SUPABASE_SERVICE_ROLE_KEY) and settings.SUPABASE_STORAGE_BUCKET):
            raise RuntimeError("Supabase Storage settings are incomplete.")
        provider = settings.AI_PROVIDER.strip().lower()
        if provider not in {"auto", "openai"}:
            raise RuntimeError("Production AI_PROVIDER must be 'auto' or 'openai'.")
        if provider == "openai" and not settings.OPENAI_API_KEY:
            raise RuntimeError("AI_PROVIDER=openai requires OPENAI_API_KEY.")
        if provider == "auto" and not (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
            raise RuntimeError("Production requires at least one AI provider API key.")
        if settings.BILLING_ENFORCED and not (settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET and settings.RAZORPAY_WEBHOOK_SECRET and settings.RAZORPAY_PLAN_ID):
            raise RuntimeError("Billing enforcement requires Razorpay keys, webhook secret, and monthly plan ID.")
    if settings.ENVIRONMENT.lower() != "production" and settings.AUTO_INIT_DB and os.environ.get("SKIP_DB_INIT") != "1":
        try:
            await asyncio.wait_for(_init_database(), timeout=3.0)
        except Exception as exc:
            print(f"[Startup Notice] Database initialization skipped or timed out: {exc}")
    try:
        yield
    finally:
        await close_ai_provider_clients()
        await engine.dispose()


app = FastAPI(
    title="DIGITAL DIARY, Powered by AI",
    description="AI-assisted case registration, investigative document management, case diaries, and report generation for investigating officers.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", tags=["System"])
async def health_live():
    return {"status": "alive"}


@app.get("/health/ready", tags=["System"])
async def health_ready():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Database is not ready.")
    return {"status": "ready"}

@app.get("/", tags=["System"])
async def root():
    return {
        "system": "DIGITAL DIARY, Powered by AI",
        "status": "online",
        "docs_url": "/docs",
        "features": [
            "AI FIR and investigative document scanner",
            "Automated Day-1 Case Diary generation",
            "Tamper-proof Case Diaries with SHA-256 Audit Trail",
            "Automated Police Chargesheet Document (.docx) Generation u/s 193 BNSS"
        ]
    }

# Public: login/register.  Everything else needs a valid officer JWT.
protected = [Depends(get_current_user), Depends(require_active_subscription)]
app.include_router(auth_router)
app.include_router(billing_router)
app.include_router(case_routes, dependencies=protected)
app.include_router(chargesheet_router, dependencies=protected)
app.include_router(diaries_router, dependencies=protected)
app.include_router(case_routes_ai, dependencies=protected)
app.include_router(diary_export_router, dependencies=protected)
app.include_router(moe_router, dependencies=protected)

