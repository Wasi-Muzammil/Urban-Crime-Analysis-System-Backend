from fastapi import APIRouter, Depends, Request, Query
from typing import Optional
from app.core.security import require_admin
from app.db.connection import get_connection
from app.core.logger import log_audit

router = APIRouter()


# ── GET /admin/logs/transaction-logs ─────────────────────────────────────────
@router.get("/transaction-logs")
def get_transaction_logs(
    request:      Request,
    current_user: dict = Depends(require_admin),
    # Optional filters
    user_id:      Optional[int] = Query(None, description="Filter by user_id"),
    table_name:   Optional[str] = Query(None, description="Filter by table name e.g. Incident"),
    action_type:  Optional[str] = Query(None, description="Filter by INSERT, UPDATE or DELETE"),
    limit:        int           = Query(100,  description="Max rows to return"),
    offset:       int           = Query(0,    description="Rows to skip for pagination"),
):
    """
    Admin-only. Returns rows from transaction_logs.

    Records every INSERT / UPDATE / DELETE performed on core tables.
    Each row answers: Who (user_id), What (table + action + record_id),
    When (logged_at), Where (ip_address).

    Optional query filters:
      ?user_id=1
      ?table_name=Incident
      ?action_type=DELETE
      ?limit=50&offset=100
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Build query dynamically based on which filters were supplied
    conditions = []
    params     = []

    if user_id:
        conditions.append("tl.user_id = %s")
        params.append(user_id)
    if table_name:
        conditions.append("tl.table_name = %s")
        params.append(table_name)
    if action_type:
        conditions.append("tl.action_type = %s")
        params.append(action_type.upper())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params += [limit, offset]

    cursor.execute(
        f"""
        SELECT
            tl.transaction_id,
            tl.user_id,
            u.email        AS user_email,
            u.name         AS user_name,
            tl.table_name,
            tl.action_type,
            tl.record_id,
            tl.ip_address,
            tl.logged_at
        FROM Transaction tl
        LEFT JOIN users u ON tl.user_id = u.user_id
        {where_clause}
        ORDER BY tl.logged_at DESC
        LIMIT %s OFFSET %s
        """,
        params
    )
    logs = cursor.fetchall()

    # Total count for pagination metadata
    cursor.execute(
        f"SELECT COUNT(*) AS total FROM Transaction tl {where_clause}",
        params[:-2] if params[:-2] else []
    )
    total = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    # Write ADMIN_ACTION audit log — admin viewed transaction logs
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = (
            f"Admin '{current_user['email']}' viewed transaction logs. "
            f"Filters: user_id={user_id}, table={table_name}, action={action_type}."
        ),
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "logs":   logs,
    }


# ── GET /admin/logs/audit-logs ────────────────────────────────────────────────
@router.get("/audit-logs")
def get_audit_logs(
    request:      Request,
    current_user: dict = Depends(require_admin),
    # Optional filters
    user_id:      Optional[int] = Query(None, description="Filter by user_id"),
    event_type:   Optional[str] = Query(None, description="LOGIN | LOGOUT | ROLE_CHANGE | ADMIN_ACTION"),
    limit:        int           = Query(100,  description="Max rows to return"),
    offset:       int           = Query(0,    description="Rows to skip for pagination"),
):
    """
    Admin-only. Returns rows from audit_logs.

    Records security and system events from the auth layer.
    Each row answers: Who (user_id), What (event_type + description),
    When (logged_at), Where (ip_address).

    Optional query filters:
      ?user_id=3
      ?event_type=FAILED_LOGIN
      ?limit=50&offset=0
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    conditions = []
    params     = []

    if user_id:
        conditions.append("al.user_id = %s")
        params.append(user_id)
    if event_type:
        conditions.append("al.event_type = %s")
        params.append(event_type.upper())

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params += [limit, offset]

    cursor.execute(
        f"""
        SELECT
            al.audit_id,
            al.user_id,
            u.email        AS user_email,
            u.name         AS user_name,
            al.event_type,
            al.description,
            al.ip_address,
            al.logged_at
        FROM Audit al
        LEFT JOIN users u ON al.user_id = u.user_id
        {where_clause}
        ORDER BY al.logged_at DESC
        LIMIT %s OFFSET %s
        """,
        params
    )
    logs = cursor.fetchall()

    # Total count for pagination
    cursor.execute(
        f"SELECT COUNT(*) AS total FROM Audit al {where_clause}",
        params[:-2] if params[:-2] else []
    )
    total = cursor.fetchone()["total"]

    cursor.close()
    conn.close()

    # Note: we intentionally do NOT log an ADMIN_ACTION here to avoid
    # an infinite loop where viewing audit logs creates more audit logs.

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "logs":   logs,
    }

