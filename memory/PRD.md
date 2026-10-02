# Marca Rise — MJ AI Assistant + Certificate Verification + Admin Panel

## Original Problem
Integrate a futuristic floating AI chatbot (MJ), certificate verification, and a hidden admin panel INTO the existing Marca Rise website (React + Vite + TypeScript + wouter), without breaking the existing design, pages, or the bottom-right "Book a call" (CalendlyCard) widget.

## Architecture / Decisions
- **Frontend**: existing Vite + React 19 + TS + wouter site migrated into `/app/frontend` (supervisor runs `yarn start` -> `vite --host 0.0.0.0 --port 3000`). Tailwind already maps brand aliases to purple (#7c0ce7).
- **Backend**: FastAPI + MongoDB (Motor) in `/app/backend/server.py`. All routes under `/api`.
- **AI**: Emergent Universal Key, OpenAI `gpt-5.4` via `emergentintegrations` (server-side only). Knowledge grounded in site content (`marca_knowledge.py`).
- **Auth**: JWT admin auth (bcrypt), Bearer token; admin seeded from env; never hardcoded in frontend.
- **DB**: `certificates` (unique index on `certificate_id`), `admins`.

## Personas
- Website visitor verifying a Marca Rise internship certificate or asking about the agency.
- Admin managing certificates (CRUD, Excel import, revoke/activate).

## Core Requirements (static)
1. Preserve existing website + Book a call widget (bottom-right).
2. New MJ chatbot floats bottom-left, non-overlapping, high z-index.
3. Certificate verification via chat (DB is source of truth; no hallucination).
4. Hidden `/admin` with server-side auth, dashboard, Excel import with validation + duplicate handling.
5. No secrets in client bundle.

## Implemented (Jun 2026)
- MJ floating orb (purple gradient, rotating ring, pulse glow, float, suggestion bubbles) — bottom-left.
- Glassmorphism chat panel: MJ header + online status, state-based mascot reactions, quick actions, animated messages, typing/working state, certificate cards (verified/revoked/not-found).
- Backend `/api/chat` with certificate-ID detection + DB lookup + LLM fallback grounded in KB; follow-ups use `context_certificate`.
- Public `/api/verify/{cert_id}` (public fields only; student_id/remarks excluded).
- `/admin`: login + dashboard (stats: total/active/revoked/this-month), searchable/paginated table, add/edit modal, revoke/activate, delete (confirm), Excel upload (preview -> validate headers/rows -> duplicate skip/update -> commit), export xlsx.
- Seed certificates: MR00-XX-00000 (active), MR26-UX-00092 (revoked), MR26-WD-00210 (active).
- Testing: 21/21 backend pytest passed; all frontend flows passed (chatbot verify, LLM answer, admin login, table, Excel import). No secret leakage.

### Iteration 2 (Jun 2026)
- First-open **certificate popup** (once per session via sessionStorage; gated off `/admin`); CTA opens MJ and prefills "VERIFY ".
- Mobile chatbot moved to **left-middle** (desktop stays bottom-left); no overlap with Book a call.
- Launcher icon replaced with circular **Marca Rise logo** (marca_logo.jpg).
- Quick actions: Verify Certificate / Our Services ✨ / Meet Founders / About Marca Rise (removed "Talk with MJ" and "Meet CEO").
- MJ identity: MJ = MAJA, owner Sam; founder answers include real LinkedIn URLs (princesamuel69, sanjay-sid) rendered clickable; no-markdown persona rule.
- Admin credentials changed to saxluyz@gmail.com / 1234.
- Testing: 24/24 backend pytest passed; all iteration-2 frontend flows passed.

## Environment Variables
- Backend `.env`: MONGO_URL, DB_NAME, CORS_ORIGINS, JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, EMERGENT_LLM_KEY.
- Frontend `.env`: REACT_APP_BACKEND_URL, REACT_APP_CALENDLY_URL, REACT_APP_LINKEDIN_URL.

## Admin
- URL `/admin` — saxluyz@gmail.com / 1234 (change via backend `.env` ADMIN_PASSWORD; re-seeds on restart). Not linked in navbar/footer.

## Backlog
### P1
- Optional `/verify/:id` public page (verification currently works fully in chat + `/api/verify`).
- Tighten `extract_certificate_id` regex to reduce false positives on non-cert hyphenated tokens.
- Explicit CORS origins for production (currently `*`).
### P2
- Clean pre-existing Footer nested-anchor hydration warning.
- Streaming chat responses; web-search grounding for live public info (backend has no live browsing).
