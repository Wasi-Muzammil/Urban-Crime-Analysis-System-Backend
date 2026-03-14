from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.core.security import get_current_user
from app.services.user_logs_service import get_my_transaction_logs,get_my_audit_logs

router = APIRouter()


@router.get("/my/logs/transactions")
def fetch_my_transaction_logs(
    action_type: Optional[str] = Query(
        None,
        description=(
            "Filter by operation type. "
            "Allowed values: INSERT | UPDATE. "
            "DELETE is not available for users. "
            "Omit to get both INSERT and UPDATE."
        )
    ),
    from_date: Optional[str] = Query(
        None,
        description=(
            "Start of date range. Format: YYYY-MM-DD. "
            "If omitted with no to_date → defaults to last 24 hours."
        )
    ),
    to_date: Optional[str] = Query(
        None,
        description=(
            "End of date range (inclusive until 23:59:59). Format: YYYY-MM-DD. "
            "If omitted with no from_date → defaults to last 24 hours."
        )
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    User-only. Returns the logged-in user's own transaction logs.

    Restrictions:
      - Only shows the current user's own records (user_id from JWT)
      - action_type limited to INSERT and UPDATE — DELETE is admin-only
      - Admin transaction records are never visible here

    ── Filter combinations ──────────────────────────────────────────────────
    All logs (default 24h):
      GET /logs/my/logs/transactions

    INSERT only:
      GET /logs/my/logs/transactions?action_type=INSERT

    All in date range:
      GET /logs/my/logs/transactions?from_date=2026-03-01&to_date=2026-03-14

    INSERT in date range:
      GET /logs/my/logs/transactions?action_type=INSERT&from_date=2026-03-01&to_date=2026-03-14

    ── Response ─────────────────────────────────────────────────────────────
    {
      "user_id":    2,
      "user_email": "wasim@gmail.com",
      "user_name":  "Wasim Zammil",
      "filters_applied": {
        "action_type":     "INSERT & UPDATE",
        "from":            "2026-03-13 14:22:01",
        "to":              "2026-03-14 14:22:01",
        "date_range_note": "Default range: last 24 hours"
      },
      "total": 3,
      "logs": [
        {
          "transaction_id": 5,
          "action_type":    "INSERT",
          "table_name":     "Incident",
          "record_id":      2,
          "ip_address":     "127.0.0.1",
          "logged_at":      "14-03-2026 10:15:33"
        }
      ]
    }
    """
    return get_my_transaction_logs(
        current_user = current_user,
        action_type  = action_type,
        from_date    = from_date,
        to_date      = to_date,
    )


@router.get("/my/logs/audit")
def fetch_my_audit_logs(
    event_type: Optional[str] = Query(
        None,
        description=(
            "Filter by event type. "
            "Allowed values: LOGIN | LOGOUT. "
            "ADMIN_ACTION and ROLE_CHANGE are not available for users. "
            "Omit to get both LOGIN and LOGOUT."
        )
    ),
    from_date: Optional[str] = Query(
        None,
        description=(
            "Start of date range. Format: YYYY-MM-DD. "
            "If omitted with no to_date → defaults to last 24 hours."
        )
    ),
    to_date: Optional[str] = Query(
        None,
        description=(
            "End of date range (inclusive until 23:59:59). Format: YYYY-MM-DD. "
            "If omitted with no from_date → defaults to last 24 hours."
        )
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    User-only. Returns the logged-in user's own audit logs.

    Restrictions:
      - Only shows the current user's own records (user_id from JWT)
      - event_type limited to LOGIN and LOGOUT
      - ADMIN_ACTION and ROLE_CHANGE are permanently excluded

    ── Filter combinations ──────────────────────────────────────────────────
    All logs (default 24h):
      GET /logs/my/logs/audit

    LOGIN only:
      GET /logs/my/logs/audit?event_type=LOGIN

    All in date range:
      GET /logs/my/logs/audit?from_date=2026-03-01&to_date=2026-03-14

    LOGOUT in date range:
      GET /logs/my/logs/audit?event_type=LOGOUT&from_date=2026-03-01&to_date=2026-03-14

    ── Response ─────────────────────────────────────────────────────────────
    {
      "user_id":    2,
      "user_email": "wasim@gmail.com",
      "user_name":  "Wasim Zammil",
      "filters_applied": {
        "event_type":      "LOGIN & LOGOUT",
        "from":            "2026-03-13 14:22:01",
        "to":              "2026-03-14 14:22:01",
        "date_range_note": "Default range: last 24 hours"
      },
      "total": 2,
      "logs": [
        {
          "audit_id":    4,
          "event_type":  "LOGIN",
          "description": "User wasim@gmail.com logged in successfully.",
          "ip_address":  "127.0.0.1",
          "logged_at":   "14-03-2026 10:14:55"
        }
      ]
    }
    """
    return get_my_audit_logs(
        current_user = current_user,
        event_type   = event_type,
        from_date    = from_date,
        to_date      = to_date,
    )