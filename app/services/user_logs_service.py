from fastapi import HTTPException
from typing import Optional
from datetime import datetime, timedelta
from app.db.connection import get_connection


def get_my_transaction_logs(
    current_user: dict,
    action_type:  Optional[str] = None,
    from_date:    Optional[str] = None,
    to_date:      Optional[str] = None,
) -> dict:
    """
    Returns transaction logs for the currently logged-in user.

    Restrictions enforced:
      - user_id is always taken from JWT — user cannot query another user's logs
      - action_type limited to INSERT and UPDATE only — DELETE is admin-only
      - Records where the acting user is an admin are excluded even if
        the user somehow passes an admin's user_id (JWT prevents this anyway)

    Filters:
      action_type : INSERT | UPDATE (optional — omit to get both)
      from_date   : YYYY-MM-DD (optional)
      to_date     : YYYY-MM-DD (optional)

    Default: last 24 hours if no dates provided.
    """
    VALID_ACTION_TYPES = {"INSERT", "UPDATE"}

    if action_type and action_type.upper() not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Invalid action_type. Allowed values for users: INSERT, UPDATE"
        )

    # ── Resolve date range ────────────────────────────────────────────────────
    now = datetime.now()

    if not from_date and not to_date:
        resolved_from   = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = "Default range: last 24 hours"

    elif from_date and not to_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid from_date. Use YYYY-MM-DD.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = f"From {from_date} until now"

    elif not from_date and to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid to_date. Use YYYY-MM-DD.")
        resolved_from   = "2000-01-01 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"All records until end of {to_date}"

    else:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
            datetime.strptime(to_date,   "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date cannot be later than to_date.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"From {from_date} to {to_date} (inclusive)"

    user_id = current_user["user_id"]

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # ── Build WHERE conditions ────────────────────────────────────────────
        # action_type != 'DELETE' is hardcoded — DELETE is admin-only and
        # must never be visible to regular users regardless of what they pass
        conditions = [
            "t.user_id     = %s",
            "t.logged_at  >= %s",
            "t.logged_at  <= %s",
            "t.action_type != %s",   # always exclude DELETE
        ]
        params = [user_id, resolved_from, resolved_to, "DELETE"]

        if action_type:
            conditions.append("t.action_type = %s")
            params.append(action_type.upper())

        where_clause = " AND ".join(conditions)

        cursor.execute(
            f"""
            SELECT
                t.transaction_id,
                t.action_type,
                t.table_name,
                t.record_id,
                t.ip_address,
                t.logged_at
            FROM `Transaction` t
            JOIN users u ON t.user_id = u.user_id
            WHERE {where_clause}
              AND u.role = 'viewer'
            ORDER BY t.logged_at DESC
            """,
            tuple(params)
        )
        rows = cursor.fetchall()

        # ── Format logged_at in Python to avoid DATE_FORMAT % conflict ────────
        logs = []
        for row in rows:
            logs.append({
                "transaction_id": row["transaction_id"],
                "action_type":    row["action_type"],
                "table_name":     row["table_name"],
                "record_id":      row["record_id"],
                "ip_address":     row["ip_address"],
                "logged_at":      row["logged_at"].strftime("%d-%m-%Y %H:%M:%S")
                                  if row["logged_at"] else None,
            })

        return {
            "user_id":         user_id,
            "user_email":      current_user["email"],
            "user_name":       current_user["name"],
            "filters_applied": {
                "action_type":     action_type.upper() if action_type else "INSERT & UPDATE",
                "from":            resolved_from,
                "to":              resolved_to,
                "date_range_note": date_range_note,
            },
            "total": len(logs),
            "logs":  logs,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch transaction logs: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()


def get_my_audit_logs(
    current_user: dict,
    event_type:   Optional[str] = None,
    from_date:    Optional[str] = None,
    to_date:      Optional[str] = None,
) -> dict:
    """
    Returns audit logs for the currently logged-in user.
 
    Restrictions enforced:
      - user_id is always taken from JWT — user cannot query another user's logs
      - event_type limited to LOGIN and LOGOUT only
      - ADMIN_ACTION and ROLE_CHANGE are permanently excluded regardless
        of what the user passes — these are admin-only event types
 
    Filters:
      event_type : LOGIN | LOGOUT (optional — omit to get both)
      from_date  : YYYY-MM-DD (optional)
      to_date    : YYYY-MM-DD (optional)
 
    Default: last 24 hours if no dates provided.
    """
    VALID_EVENT_TYPES = {"LOGIN", "LOGOUT"}
 
    if event_type and event_type.upper() not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Invalid event_type. Allowed values for users: LOGIN, LOGOUT"
        )
 
    # ── Resolve date range ────────────────────────────────────────────────────
    now = datetime.now()
 
    if not from_date and not to_date:
        resolved_from   = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = "Default range: last 24 hours"
 
    elif from_date and not to_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid from_date. Use YYYY-MM-DD.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = f"From {from_date} until now"
 
    elif not from_date and to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid to_date. Use YYYY-MM-DD.")
        resolved_from   = "2000-01-01 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"All records until end of {to_date}"
 
    else:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
            datetime.strptime(to_date,   "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date cannot be later than to_date.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"From {from_date} to {to_date} (inclusive)"
 
    user_id = current_user["user_id"]
 
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
 
    try:
        # ── Build WHERE conditions ────────────────────────────────────────────
        # ADMIN_ACTION and ROLE_CHANGE are hardcoded exclusions — these must
        # never be visible to regular users regardless of what they request
        conditions = [
            "a.user_id    = %s",
            "a.logged_at >= %s",
            "a.logged_at <= %s",
            "a.event_type NOT IN (%s, %s)",   # always exclude admin-only types
        ]
        params = [user_id, resolved_from, resolved_to, "ADMIN_ACTION", "ROLE_CHANGE"]
 
        if event_type:
            conditions.append("a.event_type = %s")
            params.append(event_type.upper())
 
        where_clause = " AND ".join(conditions)
 
        cursor.execute(
            f"""
            SELECT
                a.audit_id,
                a.event_type,
                a.description,
                a.ip_address,
                a.logged_at
            FROM `Audit` a
            JOIN users u ON a.user_id = u.user_id
            WHERE {where_clause}
              AND u.role = 'viewer'
            ORDER BY a.logged_at DESC
            """,
            tuple(params)
        )
        rows = cursor.fetchall()
 
        # ── Format logged_at in Python to avoid DATE_FORMAT % conflict ────────
        logs = []
        for row in rows:
            logs.append({
                "audit_id":    row["audit_id"],
                "event_type":  row["event_type"],
                "description": row["description"],
                "ip_address":  row["ip_address"],
                "logged_at":   row["logged_at"].strftime("%d-%m-%Y %H:%M:%S")
                               if row["logged_at"] else None,
            })
 
        return {
            "user_id":         user_id,
            "user_email":      current_user["email"],
            "user_name":       current_user["name"],
            "filters_applied": {
                "event_type":      event_type.upper() if event_type else "LOGIN & LOGOUT",
                "from":            resolved_from,
                "to":              resolved_to,
                "date_range_note": date_range_note,
            },
            "total": len(logs),
            "logs":  logs,
        }
 
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch audit logs: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()
 