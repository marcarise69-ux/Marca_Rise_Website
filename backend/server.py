"""Marca Rise backend — AI assistant (MJ), certificate verification, and admin panel."""
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import re
import io
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any

from supabase import create_client, Client
import bcrypt
import jwt
import pandas as pd

from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from marca_knowledge import build_system_prompt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("marca")

# ---------------------------------------------------------------- DB
# Supabase is now the only database used by this backend.
# The secret key MUST stay in the backend .env and must never be exposed
# to the React frontend.
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]

supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY,
)

JWT_ALGORITHM = "HS256"
JWT_SECRET = os.environ["JWT_SECRET"]
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# Canonical certificate fields
CERT_FIELDS = [
    "certificate_id",
    "student_name",
    "college_name",
    "department",
    "internship_role",
    "internship_duration",
    "start_date",
    "end_date",
    "project_name",
    "technologies",
    "certificate_status",
    "issue_date",
    "student_id",
    "internship_domain",
    "mentor",
    "grade",
    "remarks",
]

# Fields safe to expose to the public verification / chatbot
PUBLIC_FIELDS = [
    "certificate_id",
    "student_name",
    "college_name",
    "department",
    "internship_role",
    "internship_duration",
    "start_date",
    "end_date",
    "project_name",
    "technologies",
    "certificate_status",
    "issue_date",
    "internship_domain",
    "mentor",
    "grade",
]


# ---------------------------------------------------------------- Supabase helpers
def sb_one(table: str, filters: Dict[str, Any]) -> Optional[dict]:
    """Return the first matching row or None."""
    query = supabase.table(table).select("*")
    for key, value in filters.items():
        query = query.eq(key, value)

    result = query.limit(1).execute()
    return result.data[0] if result.data else None


def sb_count(table: str, filters: Optional[Dict[str, Any]] = None) -> int:
    """Count rows matching simple equality/range filters."""
    query = supabase.table(table).select("id", count="exact", head=True)

    if filters:
        for key, value in filters.items():
            if isinstance(value, tuple) and len(value) == 2:
                operator, operand = value
                if operator == "gte":
                    query = query.gte(key, operand)
                elif operator == "lte":
                    query = query.lte(key, operand)
                elif operator == "gt":
                    query = query.gt(key, operand)
                elif operator == "lt":
                    query = query.lt(key, operand)
            else:
                query = query.eq(key, value)

    result = query.execute()
    return int(result.count or 0)


def sanitize_search(value: str) -> str:
    """Keep PostgREST OR/ILIKE search syntax safe."""
    return (
        str(value)
        .strip()
        .replace("%", "")
        .replace("_", " ")
        .replace(",", " ")
    )


# ---------------------------------------------------------------- Models
class AdminLogin(BaseModel):
    email: str
    password: str


class Certificate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    certificate_id: str
    student_name: str
    college_name: str = ""
    department: str = ""
    internship_role: str = ""
    internship_duration: str = ""
    start_date: str = ""
    end_date: str = ""
    project_name: str = ""
    technologies: str = ""
    certificate_status: str = "active"
    issue_date: str = ""
    student_id: str = ""
    internship_domain: str = ""
    mentor: str = ""
    grade: str = ""
    remarks: str = ""


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    context_certificate: Optional[Dict[str, Any]] = None
    history: Optional[List[Dict[str, str]]] = None


class ImportCommit(BaseModel):
    rows: List[Dict[str, Any]]
    duplicate_mode: str = "skip"  # skip | update


# ---------------------------------------------------------------- Auth helpers
def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(email: str) -> str:
    payload = {
        "sub": email,
        "role": "admin",
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=8),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


security = HTTPBearer(auto_error=False)


async def get_current_admin(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(
            creds.credentials,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )

        if payload.get("type") != "access" or payload.get("role") != "admin":
            raise HTTPException(status_code=401, detail="Invalid token")

        admin = sb_one("admins", {"email": payload["sub"]})

        if not admin:
            raise HTTPException(status_code=401, detail="Admin not found")

        return {"email": admin["email"]}

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Session expired, please log in again",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------- Certificate helpers
CERT_ID_RE = re.compile(r"[A-Z0-9]+(?:-[A-Z0-9]+)+")


def extract_certificate_id(text: str) -> Optional[str]:
    """Detect a certificate-id-like token (e.g. MR00-XX-00000)."""
    upper = text.upper()
    candidates = CERT_ID_RE.findall(upper)

    for candidate in candidates:
        if any(ch.isdigit() for ch in candidate) and len(candidate) >= 6:
            return candidate.strip("-")

    return None


def public_view(doc: dict) -> dict:
    return {key: doc.get(key, "") for key in PUBLIC_FIELDS}


def clean_cell(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and pd.isna(value):
        return ""

    value_str = str(value).strip()

    if value_str.lower() in ("nan", "nat", "none"):
        return ""

    # Trim pandas datetime tails "2026-01-01 00:00:00"
    if value_str.endswith(" 00:00:00"):
        value_str = value_str[:-9]

    return value_str


HEADER_ALIASES = {
    "certificate_id": "certificate_id",
    "certificateid": "certificate_id",
    "cert_id": "certificate_id",
    "certificate": "certificate_id",
    "id": "certificate_id",
    "certificate_no": "certificate_id",
    "student_name": "student_name",
    "name": "student_name",
    "student": "student_name",
    "college_name": "college_name",
    "college": "college_name",
    "department": "department",
    "dept": "department",
    "internship_role": "internship_role",
    "role": "internship_role",
    "internship_duration": "internship_duration",
    "duration": "internship_duration",
    "start_date": "start_date",
    "start": "start_date",
    "end_date": "end_date",
    "end": "end_date",
    "project_name": "project_name",
    "project": "project_name",
    "technologies": "technologies",
    "technology": "technologies",
    "tech": "technologies",
    "tech_stack": "technologies",
    "certificate_status": "certificate_status",
    "status": "certificate_status",
    "issue_date": "issue_date",
    "issued": "issue_date",
    "issued_date": "issue_date",
    "date_of_issue": "issue_date",
    "student_id": "student_id",
    "internship_domain": "internship_domain",
    "domain": "internship_domain",
    "mentor": "mentor",
    "grade": "grade",
    "remarks": "remarks",
    "remark": "remarks",
}


def normalize_header(header: str) -> Optional[str]:
    key = re.sub(
        r"[^a-z0-9]+",
        "_",
        str(header).strip().lower(),
    ).strip("_")

    return HEADER_ALIASES.get(key)


def normalize_status(status: str) -> str:
    status = (status or "").strip().lower()

    if status in ("revoked", "revoke", "cancelled", "canceled", "invalid"):
        return "revoked"

    if status in ("inactive", "expired"):
        return "inactive"

    return "active"


# ---------------------------------------------------------------- App
app = FastAPI(title="Marca Rise API")
api = APIRouter(prefix="/api")


@api.get("/")
async def root():
    return {"message": "Marca Rise API online"}


# ---------------------------------------------------------------- Chat
@api.post("/chat")
async def chat(req: ChatRequest):
    message = (req.message or "").strip()

    if not message:
        raise HTTPException(status_code=400, detail="Empty message")

    cert_id = extract_certificate_id(message)
    verify_intent = (
        "verify" in message.lower()
        or "certificate" in message.lower()
    )

    # ---- Certificate verification path (Supabase is source of truth)
    if cert_id and (verify_intent or "-" in cert_id):
        doc = sb_one(
            "certificates",
            {"certificate_id": cert_id.upper()},
        )

        if not doc:
            # Case-insensitive exact match.
            result = (
                supabase
                .table("certificates")
                .select("*")
                .ilike("certificate_id", cert_id.upper())
                .limit(1)
                .execute()
            )
            doc = result.data[0] if result.data else None

        if not doc:
            return {
                "type": "certificate",
                "status": "not_found",
                "mascot": "confused",
                "reply": (
                    "I couldn't find a certificate matching that ID in the "
                    "Marca Rise verification database. Please double-check "
                    "the ID and try again."
                ),
                "certificate": None,
            }

        status = normalize_status(
            doc.get("certificate_status", "active")
        )
        cert = public_view(doc)
        cert["certificate_status"] = status.upper()

        if status == "revoked":
            return {
                "type": "certificate",
                "status": "revoked",
                "mascot": "warning",
                "reply": (
                    "This certificate is currently marked as revoked in "
                    "the Marca Rise verification system."
                ),
                "certificate": cert,
            }

        return {
            "type": "certificate",
            "status": "verified",
            "mascot": "success",
            "reply": (
                "Certificate verified successfully. This is a genuine "
                "Marca Rise certificate issued to "
                f"{cert.get('student_name', 'the student')}."
            ),
            "certificate": cert,
        }

    # ---- Normal AI assistant path
    if not EMERGENT_LLM_KEY:
        return {
            "type": "text",
            "mascot": "error",
            "certificate": None,
            "reply": (
                "The AI assistant isn't configured right now. "
                "Please try again later."
            ),
        }

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        system_prompt = build_system_prompt(
            req.context_certificate
        )

        chat_client = (
            LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=req.session_id or "marca-mj",
                system_message=system_prompt,
            )
            .with_model("openai", "gpt-5.4")
        )

        # Give short recent history as context
        convo = ""

        if req.history:
            for turn in req.history[-6:]:
                role = turn.get("role", "user")
                convo += (
                    f"\n{role.upper()}: "
                    f"{turn.get('content', '')}"
                )

        text = (
            message
            if not convo
            else (
                f"Recent conversation:{convo}\n\n"
                f"Current question: {message}"
            )
        )

        reply = await chat_client.send_message(
            UserMessage(text=text)
        )
        reply_text = (
            reply
            if isinstance(reply, str)
            else str(reply)
        )

        return {
            "type": "text",
            "mascot": "explaining",
            "certificate": None,
            "reply": reply_text.strip(),
        }

    except Exception:
        logger.exception("chat error")

        return {
            "type": "text",
            "mascot": "error",
            "certificate": None,
            "reply": (
                "Sorry, I ran into a problem answering that. "
                "Please try again in a moment."
            ),
        }


# ---------------------------------------------------------------- Public verification
@api.get("/verify/{cert_id}")
async def verify_public(cert_id: str):
    result = (
        supabase
        .table("certificates")
        .select("*")
        .ilike("certificate_id", cert_id.upper())
        .limit(1)
        .execute()
    )

    doc = result.data[0] if result.data else None

    if not doc:
        return {
            "status": "not_found",
            "certificate": None,
        }

    status = normalize_status(
        doc.get("certificate_status", "active")
    )
    cert = public_view(doc)
    cert["certificate_status"] = status.upper()

    return {
        "status": "revoked" if status == "revoked" else "verified",
        "certificate": cert,
    }


# ---------------------------------------------------------------- Admin auth
@api.post("/admin/login")
async def admin_login(body: AdminLogin):
    email = body.email.strip().lower()
    admin = sb_one("admins", {"email": email})

    if not admin or not verify_password(
        body.password,
        admin["password_hash"],
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    token = create_access_token(email)

    return {
        "access_token": token,
        "email": email,
    }


@api.get("/admin/me")
async def admin_me(
    admin: dict = Depends(get_current_admin),
):
    return admin


# ---------------------------------------------------------------- Admin stats
@api.get("/admin/stats")
async def admin_stats(
    admin: dict = Depends(get_current_admin),
):
    total = sb_count("certificates")

    active_result = (
        supabase
        .table("certificates")
        .select("id", count="exact", head=True)
        .ilike("certificate_status", "active")
        .execute()
    )
    active = int(active_result.count or 0)

    revoked_result = (
        supabase
        .table("certificates")
        .select("id", count="exact", head=True)
        .ilike("certificate_status", "revoked")
        .execute()
    )
    revoked = int(revoked_result.count or 0)

    month_start = (
        datetime.now(timezone.utc)
        .replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        .isoformat()
    )

    this_month = sb_count(
        "certificates",
        {"created_at": ("gte", month_start)},
    )

    return {
        "total": total,
        "active": active,
        "revoked": revoked,
        "this_month": this_month,
    }


# ---------------------------------------------------------------- Admin certificate CRUD
@api.get("/admin/certificates")
async def list_certificates(
    admin: dict = Depends(get_current_admin),
    search: str = "",
    status: str = "",
    page: int = 1,
    limit: int = 20,
):
    page = max(1, page)
    limit = min(max(1, limit), 100)

    query = (
        supabase
        .table("certificates")
        .select("*", count="exact")
    )

    if search.strip():
        term = sanitize_search(search)

        if term:
            query = query.or_(
                ",".join([
                    f"certificate_id.ilike.%{term}%",
                    f"student_name.ilike.%{term}%",
                    f"college_name.ilike.%{term}%",
                    f"internship_role.ilike.%{term}%",
                    f"project_name.ilike.%{term}%",
                ])
            )

    if status.strip():
        query = query.ilike(
            "certificate_status",
            status.strip(),
        )

    offset = (page - 1) * limit

    result = (
        query
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )

    return {
        "items": result.data or [],
        "total": int(result.count or 0),
        "page": page,
        "limit": limit,
    }


@api.get("/admin/certificates/export")
async def export_certificates(
    admin: dict = Depends(get_current_admin),
):
    result = (
        supabase
        .table("certificates")
        .select("*")
        .order("created_at", desc=True)
        .limit(100000)
        .execute()
    )

    docs = result.data or []

    df = (
        pd.DataFrame(docs, columns=CERT_FIELDS)
        if docs
        else pd.DataFrame(columns=CERT_FIELDS)
    )

    buf = io.BytesIO()

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Certificates",
        )

    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": (
                "attachment; "
                "filename=marca_rise_certificates.xlsx"
            )
        },
    )


@api.get("/admin/certificates/{cert_id}")
async def get_certificate(
    cert_id: str,
    admin: dict = Depends(get_current_admin),
):
    result = (
        supabase
        .table("certificates")
        .select("*")
        .ilike("certificate_id", cert_id.upper())
        .limit(1)
        .execute()
    )

    doc = result.data[0] if result.data else None

    if not doc:
        raise HTTPException(
            status_code=404,
            detail="Certificate not found",
        )

    return doc


async def _upsert_certificate(data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()

    data["certificate_id"] = (
        data["certificate_id"]
        .strip()
        .upper()
    )
    data["certificate_status"] = normalize_status(
        data.get("certificate_status", "active")
    )

    existing = sb_one(
        "certificates",
        {"certificate_id": data["certificate_id"]},
    )

    if existing:
        data["updated_at"] = now

        (
            supabase
            .table("certificates")
            .update(data)
            .eq("certificate_id", data["certificate_id"])
            .execute()
        )

        return {"action": "updated"}

    data["created_at"] = now
    data["updated_at"] = now

    (
        supabase
        .table("certificates")
        .insert(data)
        .execute()
    )

    return {"action": "created"}


@api.post("/admin/certificates")
async def create_certificate(
    cert: Certificate,
    admin: dict = Depends(get_current_admin),
):
    data = cert.model_dump()
    return await _upsert_certificate(data)


@api.put("/admin/certificates/{cert_id}")
async def update_certificate(
    cert_id: str,
    cert: Certificate,
    admin: dict = Depends(get_current_admin),
):
    data = cert.model_dump()
    data["certificate_id"] = cert_id.upper()

    await _upsert_certificate(data)

    return {"action": "saved"}


@api.patch("/admin/certificates/{cert_id}/status")
async def set_status(
    cert_id: str,
    body: Dict[str, str],
    admin: dict = Depends(get_current_admin),
):
    status = normalize_status(
        body.get("status", "active")
    )

    result = (
        supabase
        .table("certificates")
        .update({
            "certificate_status": status,
            "updated_at": datetime.now(
                timezone.utc
            ).isoformat(),
        })
        .ilike("certificate_id", cert_id.upper())
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Certificate not found",
        )

    return {
        "certificate_id": cert_id.upper(),
        "certificate_status": status,
    }


@api.delete("/admin/certificates/{cert_id}")
async def delete_certificate(
    cert_id: str,
    admin: dict = Depends(get_current_admin),
):
    result = (
        supabase
        .table("certificates")
        .delete()
        .ilike("certificate_id", cert_id.upper())
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Certificate not found",
        )

    return {"deleted": cert_id.upper()}


# ---------------------------------------------------------------- Excel import
@api.post("/admin/certificates/import/preview")
async def import_preview(
    admin: dict = Depends(get_current_admin),
    file: UploadFile = File(...),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="Please upload an .xlsx or .xls file",
        )

    content = await file.read()

    try:
        df = pd.read_excel(
            io.BytesIO(content),
            dtype=str,
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not read the spreadsheet. "
                "Ensure it is a valid Excel file."
            ),
        )

    # Map headers
    col_map: Dict[str, str] = {}

    for col in df.columns:
        canon = normalize_header(col)

        if canon:
            col_map[col] = canon

    mapped_fields = set(col_map.values())

    if (
        "certificate_id" not in mapped_fields
        or "student_name" not in mapped_fields
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required columns. The sheet must include "
                "at least 'Certificate ID' and 'Student Name'."
            ),
        )

    rows: List[dict] = []
    errors: List[dict] = []
    seen_ids = set()

    for idx, raw in df.iterrows():
        record: Dict[str, Any] = {
            field: ""
            for field in CERT_FIELDS
        }

        for col, canon in col_map.items():
            record[canon] = clean_cell(
                raw.get(col)
            )

        rownum = int(idx) + 2
        cid = (
            record.get("certificate_id", "")
            .strip()
            .upper()
        )
        record["certificate_id"] = cid

        if not cid:
            errors.append({
                "row": rownum,
                "message": "Missing Certificate ID",
            })
            continue

        if not record.get("student_name"):
            errors.append({
                "row": rownum,
                "message": (
                    f"Missing Student Name for {cid}"
                ),
            })
            continue

        if cid in seen_ids:
            errors.append({
                "row": rownum,
                "message": (
                    "Duplicate Certificate ID within file: "
                    f"{cid}"
                ),
            })
            continue

        seen_ids.add(cid)

        record["certificate_status"] = normalize_status(
            record.get("certificate_status", "active")
        )

        rows.append(record)

    existing_ids: List[str] = []

    if rows:
        ids = [
            row["certificate_id"]
            for row in rows
        ]

        result = (
            supabase
            .table("certificates")
            .select("certificate_id")
            .in_("certificate_id", ids)
            .execute()
        )

        existing_ids = [
            row["certificate_id"]
            for row in (result.data or [])
        ]

    return {
        "total": len(rows),
        "rows": rows,
        "errors": errors,
        "existing_ids": existing_ids,
        "existing_count": len(existing_ids),
    }


@api.post("/admin/certificates/import/commit")
async def import_commit(
    body: ImportCommit,
    admin: dict = Depends(get_current_admin),
):
    inserted = 0
    updated = 0
    skipped = 0

    now = datetime.now(timezone.utc).isoformat()

    for raw in body.rows:
        cid = (
            str(raw.get("certificate_id", ""))
            .strip()
            .upper()
        )

        if not cid:
            continue

        record = {
            field: str(raw.get(field, "") or "")
            for field in CERT_FIELDS
        }

        record["certificate_id"] = cid
        record["certificate_status"] = normalize_status(
            record.get("certificate_status", "active")
        )

        existing = sb_one(
            "certificates",
            {"certificate_id": cid},
        )

        if existing:
            if body.duplicate_mode == "update":
                record["updated_at"] = now

                (
                    supabase
                    .table("certificates")
                    .update(record)
                    .eq("certificate_id", cid)
                    .execute()
                )

                updated += 1
            else:
                skipped += 1

        else:
            record["created_at"] = now
            record["updated_at"] = now

            (
                supabase
                .table("certificates")
                .insert(record)
                .execute()
            )

            inserted += 1

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get(
        "CORS_ORIGINS",
        "*",
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- Startup
@app.on_event("startup")
async def startup():
    """
    Supabase handles table indexes/constraints in PostgreSQL.
    Therefore, no MongoDB-style create_index calls are needed here.
    """

    try:
        # Confirm that the required tables exist and are reachable.
        supabase.table("certificates").select(
            "id"
        ).limit(1).execute()

        supabase.table("admins").select(
            "id"
        ).limit(1).execute()

    except Exception as exc:
        logger.exception(
            "Supabase database check failed. "
            "Create the certificates and admins tables first."
        )
        raise RuntimeError(
            "Supabase database is not ready. "
            "Check SUPABASE_URL/SUPABASE_SECRET_KEY and "
            "make sure the certificates and admins tables exist."
        ) from exc

    admin_email = (
        os.environ
        .get(
            "ADMIN_EMAIL",
            "admin@marcarise.in",
        )
        .strip()
        .lower()
    )

    admin_password = os.environ.get(
        "ADMIN_PASSWORD",
        "admin123",
    )

    existing = sb_one(
        "admins",
        {"email": admin_email},
    )

    if not existing:
        supabase.table("admins").insert({
            "email": admin_email,
            "password_hash": hash_password(
                admin_password
            ),
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
        }).execute()

        logger.info(
            "Seeded admin %s",
            admin_email,
        )

    elif not verify_password(
        admin_password,
        existing["password_hash"],
    ):
        (
            supabase
            .table("admins")
            .update({
                "password_hash": hash_password(
                    admin_password
                ),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            })
            .eq("email", admin_email)
            .execute()
        )

        logger.info(
            "Updated admin password for %s",
            admin_email,
        )

    # Write test credentials for local/dev environment.
    try:
        mem = Path("/app/memory")
        mem.mkdir(exist_ok=True)

        (
            mem / "test_credentials.md"
        ).write_text(
            "# Test Credentials\n\n"
            "## Admin Panel (/admin)\n"
            f"- URL: /admin\n"
            f"- Email: {admin_email}\n"
            f"- Password: {admin_password}\n\n"
            "## Endpoints\n"
            "- POST /api/admin/login\n"
            "- GET /api/admin/me\n"
            "- GET /api/admin/stats\n"
            "- GET /api/admin/certificates\n"
            "- POST /api/admin/certificates/import/preview\n"
            "- POST /api/admin/certificates/import/commit\n"
            "- POST /api/chat\n"
            "- GET /api/verify/{cert_id}\n"
        )

    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown():
    # Supabase Python client does not require the MongoDB-style
    # client.close() used by the old Motor implementation.
    pass
