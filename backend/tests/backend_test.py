"""Backend tests for Marca Rise: admin auth, certificates CRUD, chat, verify, excel import."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to frontend/.env
    from pathlib import Path
    env = Path("/app/frontend/.env").read_text()
    for line in env.splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"
ADMIN_EMAIL = "saxluyz@gmail.com"
ADMIN_PASSWORD = "1234"
SAMPLE_XLSX = "/app/sample_certificates.xlsx"


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="session")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- Admin auth ----------
class TestAdminAuth:
    def test_login_wrong_password(self):
        r = requests.post(f"{API}/admin/login", json={"email": ADMIN_EMAIL, "password": "wrong"}, timeout=15)
        assert r.status_code == 401

    def test_login_success(self, token):
        assert isinstance(token, str) and len(token) > 20

    def test_protected_stats_requires_auth(self):
        r = requests.get(f"{API}/admin/stats", timeout=15)
        assert r.status_code in (401, 403)

    def test_protected_certs_requires_auth(self):
        r = requests.get(f"{API}/admin/certificates", timeout=15)
        assert r.status_code in (401, 403)

    def test_protected_import_requires_auth(self):
        r = requests.post(f"{API}/admin/certificates/import/commit", json={"rows": [], "duplicate_mode": "skip"}, timeout=15)
        assert r.status_code in (401, 403)


# ---------- Admin stats & list ----------
class TestAdminData:
    def test_stats(self, auth_headers):
        r = requests.get(f"{API}/admin/stats", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ("total", "active", "revoked", "this_month"):
            assert k in d
            assert isinstance(d[k], int)

    def test_list_pagination(self, auth_headers):
        r = requests.get(f"{API}/admin/certificates?page=1&limit=5", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        assert d["limit"] == 5

    def test_list_search(self, auth_headers):
        r = requests.get(f"{API}/admin/certificates?search=MR00-XX-00000", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["total"] >= 1
        assert any(i["certificate_id"] == "MR00-XX-00000" for i in d["items"])

    def test_list_status_filter(self, auth_headers):
        r = requests.get(f"{API}/admin/certificates?status=revoked", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        for i in r.json()["items"]:
            assert i["certificate_status"].lower() == "revoked"


# ---------- Chat / verification ----------
class TestChatVerification:
    def test_verify_active(self):
        r = requests.post(f"{API}/chat", json={"message": "Verify MR00-XX-00000"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "certificate"
        assert d["status"] == "verified"
        assert d["mascot"] == "success"
        cert = d["certificate"]
        assert cert is not None
        assert cert["certificate_id"] == "MR00-XX-00000"
        # public fields only
        assert "student_id" not in cert
        assert "remarks" not in cert

    def test_verify_revoked(self):
        r = requests.post(f"{API}/chat", json={"message": "Verify MR26-UX-00092"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "revoked"
        assert d["mascot"] == "warning"

    def test_verify_not_found(self):
        r = requests.post(f"{API}/chat", json={"message": "Verify MR26-XX-99999"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "not_found"
        assert d["mascot"] == "confused"

    def test_general_ceo(self):
        r = requests.post(f"{API}/chat", json={"message": "Who is the CEO of Marca Rise?"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "text"
        assert "sam" in d.get("reply", "").lower()

    def test_followup_with_context(self):
        # First fetch cert
        r = requests.post(f"{API}/chat", json={"message": "Verify MR00-XX-00000"}, timeout=30)
        cert = r.json()["certificate"]
        r2 = requests.post(f"{API}/chat", json={
            "message": "What project did this student work on?",
            "context_certificate": cert,
        }, timeout=60)
        assert r2.status_code == 200
        d = r2.json()
        assert d["type"] == "text"
        # Should reference CRM
        assert "crm" in d.get("reply", "").lower()


# ---------- Iteration 2: MJ identity, founders, services ----------
class TestMJPersona:
    def test_mj_identity_and_owner(self):
        r = requests.post(f"{API}/chat", json={"message": "What is the full form of MJ and who is your owner?"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        assert d["type"] == "text"
        reply = d.get("reply", "")
        assert "MAJA" in reply
        assert "Sam" in reply
        assert "**" not in reply

    def test_founders_with_linkedin_urls(self):
        r = requests.post(f"{API}/chat", json={"message": "Who are the founders of Marca Rise?"}, timeout=60)
        assert r.status_code == 200
        d = r.json()
        reply = d.get("reply", "")
        assert "Sam" in reply
        assert "Sanjay" in reply
        assert "Co-Founder" in reply or "co-founder" in reply.lower()
        assert "CEO" in reply
        assert "COO" in reply
        assert "https://www.linkedin.com/in/princesamuel69/" in reply
        assert "https://www.linkedin.com/in/sanjay-sid/" in reply
        assert "**" not in reply

    def test_services_list(self):
        r = requests.post(f"{API}/chat", json={"message": "What services does Marca Rise offer?"}, timeout=60)
        assert r.status_code == 200
        reply = r.json().get("reply", "").lower()
        # Real services from KB
        expected = [
            "social media",
            "short form",
            "branding",
            "web design",
            "ui/ux",
            "content strategy",
        ]
        for term in expected:
            assert term in reply, f"missing '{term}' in reply: {reply[:400]}"


# ---------- Excel import + verify ----------
class TestExcelImport:
    def test_preview(self, auth_headers):
        with open(SAMPLE_XLSX, "rb") as f:
            files = {"file": ("sample_certificates.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
            r = requests.post(f"{API}/admin/certificates/import/preview", headers=auth_headers, files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 3
        assert d["existing_count"] == 1
        assert "MR00-XX-00000" in d["existing_ids"]
        # store rows for commit test
        TestExcelImport.rows = d["rows"]

    def test_commit_skip(self, auth_headers):
        # ensure new ids don't exist yet
        for cid in ("MR26-DS-00500", "MR26-DS-00501"):
            requests.delete(f"{API}/admin/certificates/{cid}", headers=auth_headers, timeout=15)
        r = requests.post(f"{API}/admin/certificates/import/commit", headers=auth_headers,
                          json={"rows": TestExcelImport.rows, "duplicate_mode": "skip"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["inserted"] == 2
        assert d["skipped"] == 1
        assert d["updated"] == 0

    def test_commit_update(self, auth_headers):
        r = requests.post(f"{API}/admin/certificates/import/commit", headers=auth_headers,
                          json={"rows": TestExcelImport.rows, "duplicate_mode": "update"}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["updated"] >= 1

    def test_public_verify_new(self):
        r = requests.get(f"{API}/verify/MR26-DS-00500", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "verified"
        assert d["certificate"]["certificate_id"] == "MR26-DS-00500"

    def test_chat_verify_new(self):
        r = requests.post(f"{API}/chat", json={"message": "Verify MR26-DS-00500"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "verified"

    def test_patch_status_revoke(self, auth_headers):
        r = requests.patch(f"{API}/admin/certificates/MR26-DS-00500/status",
                           headers=auth_headers, json={"status": "revoked"}, timeout=15)
        assert r.status_code == 200
        assert r.json()["certificate_status"] == "revoked"
        # verify public reflects it
        v = requests.get(f"{API}/verify/MR26-DS-00500", timeout=15).json()
        assert v["status"] == "revoked"

    def test_delete(self, auth_headers):
        r = requests.delete(f"{API}/admin/certificates/MR26-DS-00500", headers=auth_headers, timeout=15)
        assert r.status_code == 200
        # cleanup other
        requests.delete(f"{API}/admin/certificates/MR26-DS-00501", headers=auth_headers, timeout=15)
        # verify gone
        v = requests.get(f"{API}/verify/MR26-DS-00500", timeout=15).json()
        assert v["status"] == "not_found"
