
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import RedirectResponse
from app.core.security import get_current_user
from urllib.parse import urlencode
from jose import jwt
import httpx
import os

from app.db.connection import get_connection
from app.core.logger import log_audit          # ← audit logging

router = APIRouter()

SECRET_KEY         = os.getenv("SECRET_KEY")
ALGORITHM          = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI         = os.getenv("GOOGLE_REDIRECT_URI")


def create_jwt_token(email: str) -> str:
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY environment variable is not set")
    expire  = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ── Step 1: Redirect to Google consent screen ─────────────────────────────────
@router.get("/google")
async def login_via_google():
    """Redirects the browser to Google's OAuth consent screen."""
    if not GOOGLE_CLIENT_ID or not REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_CLIENT_ID or GOOGLE_REDIRECT_URI env var is not set."
        )
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "consent",
    }
    return RedirectResponse(url=f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


# ── Step 2: Callback — exchange code, upsert user, issue JWT ─────────────────
@router.get("/google/callback")
async def auth_google_callback(
    request: Request,               # ← needed for ip_address
    code:    str = None,
    error:   str = None,
):
    """
    Exchanges authorization code for tokens, upserts user in DB,
    issues a JWT, and returns it as JSON.

    Audit log events written here:
      LOGIN        → on every successful authentication
    """
    ip = request.client.host        # captured once, reused in all log calls

    # ── User denied Google consent ────────────────────────────────────────────
    if error:
        raise HTTPException(status_code=400, detail="Access denied by user.")

    if not code:
        raise HTTPException(status_code=400, detail="No authorization code received.")

    # ── Exchange code for tokens ──────────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if token_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to exchange token with Google.")

    token_data = token_response.json()

    # ── Fetch Google user info ────────────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        userinfo_response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {token_data['access_token']}"},
        )

    if userinfo_response.status_code != 200:
        raise HTTPException(status_code=502, detail="Failed to fetch user info from Google.")

    user_info   = userinfo_response.json()
    email       = user_info.get("email")
    expires_in  = token_data.get("expires_in")
    expiry_date = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None

    # ── Upsert user in DB (raw SQL) ───────────────────────────────────────────
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE google_id = %s OR email = %s",
        (user_info.get("sub"), email)
    )
    db_user           = cursor.fetchone()
    new_refresh_token = token_data.get("refresh_token")

    if not db_user:
        # First-time login — insert new user with role 'viewer'
        cursor.execute(
            """INSERT INTO users
                   (email, name, google_id, role, access_token, refresh_token, token_expiry)
               VALUES (%s, %s, %s, 'viewer', %s, %s, %s)""",
            (
                email, user_info.get("name"), user_info.get("sub"),
                token_data.get("access_token"), new_refresh_token, expiry_date,
            )
        )
    else:
        # Returning user — update tokens
        # Google only sends refresh_token on first login or after re-consent
        if new_refresh_token:
            cursor.execute(
                """UPDATE users
                   SET name=%s, google_id=%s, access_token=%s,
                       refresh_token=%s, token_expiry=%s
                   WHERE email=%s""",
                (
                    user_info.get("name"), user_info.get("sub"),
                    token_data.get("access_token"),
                    new_refresh_token, expiry_date, email,
                )
            )
        else:
            cursor.execute(
                """UPDATE users
                   SET name=%s, google_id=%s, access_token=%s, token_expiry=%s
                   WHERE email=%s""",
                (
                    user_info.get("name"), user_info.get("sub"),
                    token_data.get("access_token"), expiry_date, email,
                )
            )

    conn.commit()

    # Fetch the saved user row to get user_id and role for the audit log
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    final_user = cursor.fetchone()
    cursor.close()
    conn.close()

    # ── Write LOGIN audit log ─────────────────────────────────────────────────
    log_audit(
        event_type  = "LOGIN",
        description = f"User '{email}' authenticated via Google OAuth. Role: {final_user['role']}",
        ip_address  = ip,
        user_id     = final_user["user_id"],
    )

    # ── Return JWT as JSON ────────────────────────────────────────────────────
    return {
        "access_token": create_jwt_token(email),
        "token_type":   "bearer",
        "email":        email,
        "name":         final_user.get("name"),
        "role":         final_user.get("role"),
    }


# ── Logout ────────────────────────────────────────────────────────────────────
@router.post("/logout")
async def logout(
    request:      Request,
    current_user: dict = Depends(get_current_user),   # ← properly injected
):
    log_audit(
        event_type  = "LOGOUT",
        description = f"User '{current_user['email']}' logged out.",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
    return {"message": "Logged out. Please discard your token on the client side."}