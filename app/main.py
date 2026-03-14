from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import (
    incident_router
)
from app.routers.user_logs_router import router as user_logs_router
from app.routers.search_router import router as search_router
from app.admin.admin_logs_router import router as admin_logs_router
from app.admin.admin_user_router import router as admin_users_router
from app.admin.admin_role_router import router as admin_role_router
from app.admin.admin_search_router import router as admin_search_router
from app.auth import router


# ── App instance ──────────────────────────────────────────────────────────────
app = FastAPI(
    title       = "Urban Crime Analysis System",
    description = "FastAPI + Raw SQL + MySQL + Google OAuth + JWT",
    version     = "4.0.0",
)

# CORS — adjust origins for production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes (no JWT required)
app.include_router(router.router, prefix="/auth", tags=["Auth"])

# ── Search (JWT required) ─────────────────────────────────────
app.include_router(search_router,       prefix="/search",   tags=["Search"])
app.include_router(user_logs_router, prefix="/logs", tags=["User Logs"])

# Protected API routes
app.include_router(incident_router.router,       prefix="/incidents",       tags=["Incidents"])


# ── Admin-only routes ─────────────────────────────────────────
app.include_router(admin_logs_router, prefix="/admin/logs", tags=["Admin Logs"])
app.include_router(admin_role_router, prefix="/admin/role", tags=["Admin"])
app.include_router(admin_search_router, prefix="/admin", tags=["Admin Search"])
app.include_router(admin_users_router, prefix="/admin", tags=["Admin"])

@app.get("/", tags=["Health"])
def root():
    return {"message": "UCAS API running.", "version": "5.0.0"}
