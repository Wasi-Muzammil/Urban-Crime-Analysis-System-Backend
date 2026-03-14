from fastapi import APIRouter, Depends, Request, Query
from app.core.security import require_admin, change_user_role,get_current_user

router = APIRouter()


@router.patch("/users/{user_id}/role")
def change_role(
    user_id:      int,
    request:      Request,
    new_role:     str  = Query(..., description="New role for the user. Must be 'admin' or 'viewer'."),
    current_user: dict = Depends(get_current_user),
):
    """
    Admin-only. Changes a user's role to 'admin' or 'viewer'.

    The ROLE_CHANGE audit log is written automatically inside
    change_user_role() in security.py — no extra logging needed here.

    Rules:
      - Target user must exist in the users table
      - new_role must be exactly 'admin' or 'viewer'
      - Admin cannot accidentally pass any other value (422 returned)

    Usage:
      PATCH /admin/users/3/role?new_role=admin   ← promotes viewer to admin
      PATCH /admin/users/3/role?new_role=viewer  ← demotes admin to viewer

    Response:
    {
      "message":  "Role updated successfully.",
      "user_id":  3,
      "old_role": "viewer",
      "new_role": "admin"
    }
    """
    return change_user_role(
        target_user_id = user_id,
        new_role       = new_role,
        admin_user     = current_user,
        ip_address     = request.client.host,
    )