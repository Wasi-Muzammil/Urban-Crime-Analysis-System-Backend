from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class GoogleAuthURLResponse(BaseModel):
    """Response from GET /auth/google — client opens this URL in browser."""
    auth_url: str


class TokenResponse(BaseModel):
    """
    Response from GET /auth/google/callback after successful OAuth flow.
    Client stores access_token and sends it as:
        Authorization: Bearer <access_token>
    """
    access_token: str
    token_type:   str = "bearer"
    email:        str
    name:         Optional[str] = None
    role:         str           # 'admin' or 'viewer'


class UserPublic(BaseModel):
    """Safe user info returned from protected endpoints."""
    user_id:    int
    email:      str
    name:       Optional[str] = None
    role:       str
    created_at: Optional[datetime] = None