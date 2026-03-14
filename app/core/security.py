from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import SECRET_KEY, ALGORITHM, JWT_EXPIRE_MINUTES
from app.db.connection import get_connection

bearer_scheme = HTTPBearer()


def create_jwt_token(email: str) -> str:
    """Create a signed JWT that expires in JWT_EXPIRE_MINUTES."""
    if not SECRET_KEY:
        raise RuntimeError("SECRET_KEY env variable is not set")
    expire  = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_jwt_token(token: str) -> dict:
    """Decode and verify a JWT. Raises 401 on failure."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """
    FastAPI dependency — extracts and validates JWT from Authorization header.
    Returns the full user row dict from the DB.

    Usage in any route:
        current_user: dict = Depends(get_current_user)
    """
    payload = decode_jwt_token(credentials.credentials)
    email   = payload.get("sub")
    if not email:
        raise HTTPException(status_code=401, detail="Token payload invalid.")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    FastAPI dependency — same as get_current_user but blocks non-admins.

    Usage in any route:
        current_user: dict = Depends(require_admin)
    """
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


def change_user_role(
    target_user_id: int,
    new_role:       str,
    admin_user:     dict,
    ip_address:     str = None,
) -> dict:
    """
    Promotes or demotes a user's role.
    Writes a ROLE_CHANGE audit log entry.
    Called from the admin router, not used as a dependency.

    Args:
        target_user_id : user_id of the user whose role is being changed
        new_role       : 'admin' or 'viewer'
        admin_user     : the admin performing the change (from Depends(require_admin))
        ip_address     : from request.client.host
    """
    from app.core.logger import log_audit   # local import avoids circular dependency

    if new_role not in ("admin", "viewer"):
        raise HTTPException(status_code=422, detail="role must be 'admin' or 'viewer'.")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch target user before changing so we can log old → new role
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (target_user_id,))
    target = cursor.fetchone()
    if not target:
        cursor.close()
        conn.close()
        raise HTTPException(status_code=404, detail="Target user not found.")

    old_role = target["role"]

    cursor.execute(
        "UPDATE users SET role = %s WHERE user_id = %s",
        (new_role, target_user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

    # Write ROLE_CHANGE audit log
    log_audit(
        event_type  = "ROLE_CHANGE",
        description = (
            f"Admin '{admin_user['email']}' changed role of user "
            f"'{target['email']}' from '{old_role}' to '{new_role}'."
        ),
        ip_address  = ip_address,
        user_id     = admin_user["user_id"],
    )

    return {
        "message":   "Role updated successfully.",
        "user_id":   target_user_id,
        "old_role":  old_role,
        "new_role":  new_role,
    }