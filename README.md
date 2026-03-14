# Urban Crime Analysis System (UCAS) — Backend v2

FastAPI + Raw SQL + MySQL + Google OAuth 2.0 + JWT Authorization

## Quick Start
1. python -m venv venv && source venv/bin/activate  (Win: venv\Scripts\activate)
2. pip install -r requirements.txt
3. Edit .env with your credentials
4. Open MySQL Workbench -> run app/db/schema.sql
5. uvicorn app.main:app --reload
6. Open http://localhost:8000/docs

## Auth Flow
  Browser -> GET /auth/google
          -> Google Consent Screen
          -> GET /auth/google/callback?code=...
          -> Redirects to FRONTEND_URL/auth/callback?token=JWT&name=...&email=...
  Frontend stores the JWT and sends it as:
      Authorization: Bearer <token>

## Role System
  - viewer : can read all data, create incidents/victims/suspects
  - admin  : full CRUD + can update user roles, delete incidents

## Business Rules Enforced
  - Low/Medium severity  -> exactly 1 police station
  - High severity        -> 1 or more police stations
  - Incident deletion    -> only allowed when CaseStatus = 'Rejected'
  - reported_at          -> auto-set by DB (never by user)
