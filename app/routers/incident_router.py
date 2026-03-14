from fastapi import APIRouter, HTTPException, Depends, Request
from app.models.incident import IncidentWithStations
from app.services import incident_service
from app.core.security import get_current_user, require_admin
from app.models.incident import CrimeReportForm, MediaUpdateForm
from app.services.incident_service import submit_crime_report, update_incident_media,get_my_incidents,get_incident_detail


router = APIRouter()


# ── Static routes first ───────────────────────────────────────────────────────

@router.post("/report", status_code=201)
def file_crime_report(
    request:      Request,
    form:         CrimeReportForm,
    current_user: dict = Depends(get_current_user),
):
    """
    Crime Application Form — filed by a logged-in victim.
    ip_address is extracted from the request and passed to the service
    so it can be written into transaction_logs.
    """
    return submit_crime_report(form, current_user, ip_address=request.client.host)


@router.get("/my-incidents")
def my_incidents(current_user: dict = Depends(get_current_user)):
    """Returns all incidents filed by the currently logged-in victim."""
    return get_my_incidents(current_user)


# ── Dynamic routes below all static routes ───────────────────────────────────

@router.get("/{incident_id}")
def get_single_incident(
    incident_id:  int,
    current_user: dict = Depends(get_current_user),
):
    """
    Full detail of one incident card — all tables joined.
    Ownership verified before any data is returned.
    """
    return get_incident_detail(incident_id, current_user)


@router.patch("/{incident_id}/media")
def update_media(
    incident_id:  int,
    request:      Request,
    form:         MediaUpdateForm,
    current_user: dict = Depends(get_current_user),
):
    """
    Victim updates cctv_footage_path or picture_path on their incident.
    Ownership verified. Transaction log written on success.
    """
    return update_incident_media(
        incident_id, form, current_user, ip_address=request.client.host
    )