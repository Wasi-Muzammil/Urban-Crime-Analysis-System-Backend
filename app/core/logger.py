"""
app/core/logger.py

Central logging utility for UCAS.
All transaction and audit log writes go through these two functions.
Never call the DB directly from routers/services for logging —
always use these helpers so the format stays consistent.
"""

from app.db.connection import get_connection


# ── Transaction Logger ────────────────────────────────────────────────────────

def log_transaction(
    user_id:     int,
    table_name:  str,
    action_type: str,   # 'INSERT' | 'UPDATE' | 'DELETE'
    record_id:   int,
    ip_address:  str = None,
) -> None:
    """
    Insert one row into transaction_logs.

    Called from service layer after every successful INSERT / UPDATE / DELETE
    on core tables: Incident, Victim, Suspect, Location, PoliceStation,
    CaseStatus, Incident_Victim, Incident_Suspect, Incident_PoliceStation.

    Args:
        user_id     : from JWT current_user["user_id"]
        table_name  : name of the table that was modified
        action_type : 'INSERT', 'UPDATE', or 'DELETE'
        record_id   : primary key of the row that was affected
        ip_address  : from request.client.host (passed in from router)
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO `Transaction`
                   (user_id, table_name, action_type, record_id, ip_address)
               VALUES (%s, %s, %s, %s, %s)""",
            (user_id, table_name, action_type.upper(), record_id, ip_address)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


# ── Audit Logger ──────────────────────────────────────────────────────────────

def log_audit(
    event_type:  str,           
    description: str,
    ip_address:  str  = None,
    user_id:     int  = None,   # None for FAILED_LOGIN (no valid user yet)
) -> None:
    """
    Insert one row into audit_logs.

    Called from:
      - auth/router.py         : LOGIN
      - auth/router.py         : LOGOUT (when endpoint is added)
      - admin/logs_router.py   : ADMIN_ACTION (when admin views/changes data)
      - security.py            : ROLE_CHANGE (when admin promotes a user)

    Args:
        event_type  : one of the ENUM values in audit_logs.event_type
        description : plain-English description, e.g. "User wasim@gmail.com logged in"
        ip_address  : from request.client.host
        user_id     : None is valid — FAILED_LOGIN has no authenticated user
    """
    conn   = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
             """INSERT INTO Audit
                (user_id, event_type, description, ip_address)
            VALUES (%s, %s, %s, %s)""",
            (user_id, event_type.upper(), description, ip_address)
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()