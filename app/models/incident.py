from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

IncidentCategory = Literal['theft','robbery','assault','homicide','cybercrime','fraud']
IncidentSeverity = Literal['Low','Medium','High']

class IncidentCreate(BaseModel):
    title: Optional[str] = None
    category_name: IncidentCategory
    incident_datetime: datetime
    description: Optional[str] = None
    crime_severity: IncidentSeverity
    location_id: int
    status_id: int

class IncidentResponse(IncidentCreate):
    incident_id: int
    reported_at: Optional[datetime] = None

class IncidentWithStations(IncidentCreate):
    """Used when creating an incident — supply station_ids list."""
    station_ids: list[int]  # 1 for Low/Medium, 1+ for High

class CrimeReportForm(BaseModel):
    """
    Payload for POST /incidents/report

    REQUIRED:
      title, category_name, incident_datetime,
      area_name, city, victim_cnic, victim_phone

    OPTIONAL:
      description, street_address, postal_code,
      cctv_footage_paths (list, one or more),
      victim_address, injury_type

    Auto-handled by backend (never send in request):
      crime_severity  -> NULL on insert, admin sets it later
      reported_at     -> auto-set by DB
      status_name     -> hardcoded 'Waiting'
      victim_name     -> from JWT (users.name)
      victim_email    -> from JWT (users.email)
      victim_id       -> same as user_id from JWT

    Admin-only (not in this form):
      All Suspect data and picture_path
    """
    # Incident
    title:              str
    category_name:      IncidentCategory
    incident_datetime:  datetime
    description:        Optional[str]       = None

    # Location
    area_name:          str
    city:               str
    street_address:     Optional[str]       = None
    postal_code:        Optional[str]       = None

    # one path
    cctv_footage_path: Optional[str] = None
    picture_path:      Optional[str] = None

    # Victim (name + email come from JWT)
    victim_cnic:        str
    victim_phone:       str
    victim_address:     Optional[str]       = None

    # Incident_Victim junction
    injury_type:        Optional[str]       = None



class MediaUpdateForm(BaseModel):
    cctv_footage_path: Optional[str] = None   # either or both, at least one required
    picture_path:      Optional[str] = None