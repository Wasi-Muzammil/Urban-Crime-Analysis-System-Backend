from fastapi import APIRouter, Depends, Request, Query
from app.core.security import require_admin
from typing import Optional
from app.core.logger import log_audit,log_transaction
from app.admin.admin_user_service import get_all_viewers,delete_incident,get_user_by_id,get_victim_by_user_id,get_user_incidents,get_user_incident_detail,validate_station_count,admin_update_incident
from app.admin.admin_schema import AdminIncidentUpdateForm
from app.admin.admin_user_service import get_user_transaction_logs,get_user_audit_logs


router = APIRouter()


@router.get("/users")
def fetch_all_users(
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns all registered users whose role is 'viewer'.
    The requesting admin himself is excluded from the results.

    Attributes returned per user:
      - user_id
      - email
      - name
      - created_at  (DD-MM-YYYY)

    Response:
    {
      "total": 3,
      "users": [
        {
          "user_id":    2,
          "email":      "wasim@gmail.com",
          "name":       "Wasim Zammil",
          "created_at": "09-03-2026"
        }
      ]
    }
    """
    result = get_all_viewers(current_user)

    log_audit(
        event_type  = "ADMIN_ACTION",
        description = f"Admin '{current_user['email']}' fetched all viewer accounts. Total: {result['total']}",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )

    return result

@router.get("/users/{user_id}")
def fetch_single_user(
    user_id:      int,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns a single user's info when their card is clicked
    on the admin dashboard.

    Attributes returned:
      - user_id
      - email
      - name

    Response:
    {
      "user_id": 2,
      "email":   "wasi@gmail.com",
      "name":    "Wasi Muzammil"
    }
    """
    result = get_user_by_id(user_id, current_user)

    log_audit(
        event_type  = "ADMIN_ACTION",
        description = f"Admin '{current_user['email']}' viewed user profile of '{result['email']}' (user_id={user_id}).",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )

    return result

@router.get("/users/{user_id}/victim")
def fetch_victim_info(
    user_id:      int,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Fetches the victim profile linked to this user.
    Uses the same user_id from GET /admin/users/{user_id} —
    victim_id in the Victim table equals user_id in the users table.

    Returns 404 if the user has never filed an incident report,
    since the Victim record is only created on first report submission.

    Response:
    {
      "victim_id": 2,
      "name":      "Wasim Zammil",
      "cnic":      "42201-22112211-1",
      "email":     "wasim@gmail.com",
      "phone":     "04422222234",
      "address":   "Karachi"
    }
    """
    result = get_victim_by_user_id(user_id)

    log_audit(
        event_type  = "ADMIN_ACTION",
        description = f"Admin '{current_user['email']}' viewed victim info for user_id={user_id}.",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )

    return result

@router.delete("/users/{user_id}/incidents/{incident_id}")
def delete_incident_endpoint(
    user_id:      int,
    incident_id:  int,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Deletes a single incident and all its linked records
    ONLY if the incident's status_name is 'Rejected'.
 
    What gets deleted:
      - Incident
      - Location         (linked to this incident)
      - CaseStatus       (linked to this incident)
      - Suspect(s)       (linked via Incident_Suspect — if any)
      - PoliceStation(s) (linked via Incident_PoliceStation — if any)
      - Junction rows    (Incident_Victim, Incident_Suspect,
                          Incident_PoliceStation) via CASCADE
 
    What is preserved:
      - Victim / users record — the user still exists and may
        have other incident reports
 
    On failure (409 Conflict):
      Returned when status is anything other than 'Rejected'.
      No data is modified.
 
    Response (success):
    {
      "message":          "Incident 5 deleted successfully.",
      "incident_id":      5,
      "user_id":          2,
      "location_deleted": 3,
      "status_deleted":   3,
      "suspects_deleted": 1,
      "stations_deleted": 2
    }
    """
    result = delete_incident(
        target_user_id = user_id,
        incident_id    = incident_id,
        admin_user     = current_user,
        ip_address     = request.client.host,
    )
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = (
            f"Admin '{current_user['email']}' deleted incident_id={incident_id} "
            f"for user_id={user_id}. "
            f"Suspects deleted: {result['suspects_deleted']}, "
            f"Stations deleted: {result['stations_deleted']}."
        ),
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result
 
@router.get("/users/{user_id}/incidents")
def fetch_user_incidents(
    user_id:      int,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns all incidents filed by a specific user.
    Shown as incident cards on page R1 after clicking a user card.
 
    Response:
    {
      "user_id": 2,
      "total": 3,
      "incidents": [
        {
          "incident_id": 1,
          "title": "Bank Robbery",
          "category_name": "robbery",
          "crime_severity": null,
          "incident_datetime": "...",
          "reported_at": "...",
          "area_name": "Gulshan",
          "city": "Karachi",
          "status_name": "Waiting"
        }
      ]
    }
    """
    result = get_user_incidents(user_id)
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = f"Admin '{current_user['email']}' viewed all incidents for user_id={user_id}. Total: {result['total']}",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result
 
 
@router.get("/users/{user_id}/incidents/{incident_id}")
def fetch_user_incident_detail(
    user_id:      int,
    incident_id:  int,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns full detail of one incident belonging to a user.
    Called when admin clicks an incident card on R1 — pre-fills the R2 form.
 
    Returns all data from:
      Incident, Location, CaseStatus, Victim, Incident_Victim,
      Suspect (if exists), Incident_Suspect,
      PoliceStation(s), Incident_PoliceStation
    """
    result = get_user_incident_detail(user_id, incident_id)
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = f"Admin '{current_user['email']}' viewed incident_id={incident_id} for user_id={user_id}.",
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result
 
 
@router.get("/incidents/{incident_id}/station-count")
def get_station_count(
    incident_id:  int,
    count:        int   = Query(..., ge=1, description="Number of police stations required"),
    request:      Request = None,
    current_user: dict  = Depends(require_admin),
):
    """
    Admin-only. Called after admin answers 'how many police stations
    do you require?' on the R2 form.
 
    Validates the requested count against the incident's crime_severity:
      Low or Medium → count must be exactly 1
      High          → count must be 2 or more
      NULL          → admin must set crime_severity first via the update form
 
    On success, returns N empty station slot templates so the frontend
    knows exactly how many PoliceStation input bars to render.
 
    Usage:
      GET /admin/incidents/1/station-count?count=3
 
    Response:
    {
      "incident_id": 1,
      "crime_severity": "High",
      "station_count": 3,
      "message": "Form updated. Please fill in 3 police station(s).",
      "station_slots": [
        {"slot": 1, "station_name": "", "city": "", "address": "", "incharge_officer_name": "", "charges_filed": 0},
        {"slot": 2, "station_name": "", "city": "", "address": "", "incharge_officer_name": "", "charges_filed": 0},
        {"slot": 3, "station_name": "", "city": "", "address": "", "incharge_officer_name": "", "charges_filed": 0}
      ]
    }
    """
    return validate_station_count(incident_id, count)
 
 
@router.put("/users/{user_id}/incidents/{incident_id}")
def update_incident(
    user_id:      int,
    incident_id:  int,
    form:         AdminIncidentUpdateForm,
    request:      Request,
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Submits the full update form for a specific incident on R2.
 
    Fields inherited from the victim's crime report (admin can correct):
      title, category_name, incident_datetime, description,
      area_name, city, street_address, postal_code,
      cctv_footage_path, victim_cnic, victim_phone,
      victim_address, injury_type
 
    Fields only admin can set:
      crime_severity   → Low | Medium | High
      suspect          → name, cnic, status, arrest_date
      police_stations  → list of N stations (count pre-validated via station-count endpoint)
 
    COALESCE logic: any field left null in the request body keeps its
    existing DB value — only explicitly provided fields are updated.
 
    Police station behaviour:
      All existing station links for this incident are replaced with
      the newly submitted list. Business rule is re-enforced:
        Low/Medium → exactly 1 station
        High       → 2 or more stations
 
    Example request body:
    {
      "crime_severity": "High",
      "suspect": {
        "name": "Ali Hassan",
        "cnic": "42101-1234567-1",
        "status": "Suspected",
        "arrest_date": "2026-03-10"
      },
      "police_stations": [
        {"station_name": "Gulshan Station", "city": "Karachi", "address": "Block 6", "incharge_officer_name": "Tariq Beg", "charges_filed": 0},
        {"station_name": "Clifton Station", "city": "Karachi", "address": "Block 2", "incharge_officer_name": "Asad Mir", "charges_filed": 0}
      ]
    }
    """
    result = admin_update_incident(
        target_user_id = user_id,
        incident_id    = incident_id,
        form           = form,
        admin_user     = current_user,
        ip_address     = request.client.host,
    )
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = (
            f"Admin '{current_user['email']}' updated incident_id={incident_id} "
            f"for user_id={user_id}."
        ),
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result

@router.get("/users/{user_id}/logs/transactions")
def fetch_user_transaction_logs(
    user_id:     int,
    request:     Request,
    action_type: Optional[str] = Query(
        None,
        description=(
            "Filter by operation type. "
            "One of: INSERT | UPDATE | DELETE. "
            "Omit to get all types."
        )
    ),
    from_date:   Optional[str] = Query(
        None,
        description=(
            "Start of date range. Format: YYYY-MM-DD. "
            "If omitted with no to_date → defaults to last 24 hours."
        )
    ),
    to_date:     Optional[str] = Query(
        None,
        description=(
            "End of date range (inclusive, until 23:59:59). Format: YYYY-MM-DD. "
            "If omitted with no from_date → defaults to last 24 hours."
        )
    ),
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns transaction logs for a specific user on page R1.
    Called from the Transaction tab when admin clicks a user card.
 
    ── Date range behaviour ─────────────────────────────────────────────────
    No dates provided       → last 24 hours (default)
    only from_date          → from_date until now
    only to_date            → all records until end of to_date
    both from_date+to_date  → exact range, to_date inclusive until 23:59:59
 
    ── Filter combinations ──────────────────────────────────────────────────
    All logs (default 24h):
      GET /admin/users/2/logs/transactions
 
    All logs, specific action:
      GET /admin/users/2/logs/transactions?action_type=INSERT
 
    All logs in date range:
      GET /admin/users/2/logs/transactions?from_date=2026-03-01&to_date=2026-03-14
 
    Specific action in date range:
      GET /admin/users/2/logs/transactions
        ?action_type=DELETE&from_date=2026-03-01&to_date=2026-03-14
 
    ── Response ─────────────────────────────────────────────────────────────
    {
      "user_id":    2,
      "user_email": "wasim@gmail.com",
      "user_name":  "Wasim Zammil",
      "filters_applied": {
        "action_type":     "INSERT",
        "from_date":       "2026-03-01 00:00:00",
        "to_date":         "2026-03-14 23:59:59",
        "date_range_note": "From 2026-03-01 to 2026-03-14 (inclusive)"
      },
      "total": 5,
      "logs": [
        {
          "transaction_id": 12,
          "action_type":    "INSERT",
          "table_name":     "Incident",
          "record_id":      3,
          "ip_address":     "127.0.0.1",
          "logged_at":      "09-03-2026 14:22:01"
        }
      ]
    }
    """
    result = get_user_transaction_logs(
        target_user_id = user_id,
        action_type    = action_type,
        from_date      = from_date,
        to_date        = to_date,
    )
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = (
            f"Admin '{current_user['email']}' viewed transaction logs "
            f"for user_id={user_id}. "
            f"Filters — action_type: {action_type or 'ALL'}, "
            f"from: {from_date or 'default'}, to: {to_date or 'default'}. "
            f"Total records returned: {result['total']}."
        ),
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result

@router.get("/users/{user_id}/logs/audit")
def fetch_user_audit_logs(
    user_id:    int,
    request:    Request,
    event_type: Optional[str] = Query(
        None,
        description=(
            "Filter by event type. "
            "One of: LOGIN | LOGOUT | ADMIN_ACTION | ROLE_CHANGE. "
            "Omit to get all event types."
        )
    ),
    from_date:  Optional[str] = Query(
        None,
        description=(
            "Start of date range. Format: YYYY-MM-DD. "
            "If omitted with no to_date → defaults to last 24 hours."
        )
    ),
    to_date:    Optional[str] = Query(
        None,
        description=(
            "End of date range (inclusive until 23:59:59). Format: YYYY-MM-DD. "
            "If omitted with no from_date → defaults to last 24 hours."
        )
    ),
    current_user: dict = Depends(require_admin),
):
    """
    Admin-only. Returns audit logs for a specific user on page R1 (Audit tab).
    user_id is passed automatically by the frontend when admin clicks a user card.
 
    ── Date range behaviour ─────────────────────────────────────────────────
    No dates provided       → last 24 hours (default)
    only from_date          → from_date until now
    only to_date            → all records until end of to_date
    both from_date+to_date  → exact range, to_date inclusive until 23:59:59
 
    ── Filter combinations ──────────────────────────────────────────────────
    All logs (default 24h):
      GET /admin/users/2/logs/audit
 
    Specific event type only:
      GET /admin/users/2/logs/audit?event_type=LOGIN
 
    All events in date range:
      GET /admin/users/2/logs/audit?from_date=2026-03-01&to_date=2026-03-14
 
    Specific event in date range:
      GET /admin/users/2/logs/audit?event_type=ROLE_CHANGE&from_date=2026-03-01&to_date=2026-03-14
 
    ── Response ─────────────────────────────────────────────────────────────
    {
      "user_id":    2,
      "user_email": "wasim@gmail.com",
      "user_name":  "Wasim Zammil",
      "filters_applied": {
        "event_type":      "LOGIN",
        "from":            "2026-03-01 00:00:00",
        "to":              "2026-03-14 23:59:59",
        "date_range_note": "From 2026-03-01 to 2026-03-14 (inclusive)"
      },
      "total": 4,
      "logs": [
        {
          "audit_id":    7,
          "event_type":  "LOGIN",
          "description": "User wasim@gmail.com logged in successfully.",
          "ip_address":  "127.0.0.1",
          "logged_at":   "09-03-2026 14:22:01"
        }
      ]
    }
    """
    result = get_user_audit_logs(
        target_user_id = user_id,
        event_type     = event_type,
        from_date      = from_date,
        to_date        = to_date,
    )
 
    log_audit(
        event_type  = "ADMIN_ACTION",
        description = (
            f"Admin '{current_user['email']}' viewed audit logs "
            f"for user_id={user_id}. "
            f"Filters — event_type: {event_type or 'ALL'}, "
            f"from: {from_date or 'default'}, to: {to_date or 'default'}. "
            f"Total records returned: {result['total']}."
        ),
        ip_address  = request.client.host,
        user_id     = current_user["user_id"],
    )
 
    return result