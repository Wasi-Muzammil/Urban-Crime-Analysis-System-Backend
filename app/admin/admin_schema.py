
from typing import List, Optional
from pydantic import BaseModel

# ── Pydantic models for the admin update form ─────────────────────────────────

class PoliceStationInput(BaseModel):
    """One police station entry in the admin form."""
    station_name:          str
    city:                  str
    address:               str
    incharge_officer_name: str
    charges_filed:         int = 0   # NUMERIC in schema, default 0


class SuspectUpdateInput(BaseModel):
    """
    Admin fills in the real suspect identity.
    picture_path already exists (uploaded by victim) — admin updates
    name, cnic, status and optionally arrest_date.
    """
    name:        str
    cnic:        str
    status:      str    # one of the 3 ENUM values + 'Suspected'
    arrest_date: Optional[str] = None   # DATE string 'YYYY-MM-DD', from Incident_Suspect


class AdminIncidentUpdateForm(BaseModel):
    """
    Full admin update form for a single incident (submitted on R2).

    Fields inherited from the victim's crime report form
    (admin can correct any of these):
      title, category_name, incident_datetime, description,
      area_name, city, street_address, postal_code,
      cctv_footage_path, victim_cnic, victim_phone,
      victim_address, injury_type

    Fields ONLY admin can set (new on this form):
      crime_severity   → required — admin must decide Low/Medium/High
      suspect          → optional — only if a suspect exists
      police_stations  → required — list of stations (count decided beforehand)
    """
    # ── From Incident table ───────────────────────────────────────────────────
    title:              Optional[str] = None
    category_name:      Optional[str] = None
    incident_datetime:  Optional[str] = None
    description:        Optional[str] = None
    crime_severity:     str           = None   # required — admin must set this

    # -- From CaseStatus Table -----------------------------------
    status_name:  Optional[str] = None   # Waiting | Accepted; Under Investigation | Investigated | Rejected

    # ── From Location table ───────────────────────────────────────────────────
    area_name:          Optional[str] = None
    city:               Optional[str] = None
    street_address:     Optional[str] = None
    postal_code:        Optional[str] = None
    cctv_footage_path:  Optional[str] = None

    # ── From Victim table ─────────────────────────────────────────────────────
    victim_cnic:        Optional[str] = None
    victim_phone:       Optional[str] = None
    victim_address:     Optional[str] = None

    # ── From Incident_Victim junction ─────────────────────────────────────────
    injury_type:        Optional[str] = None

    # ── Admin-only: Suspect info ──────────────────────────────────────────────
    suspect:            Optional[SuspectUpdateInput] = None

    # ── Admin-only: Police stations (N stations decided before form submit) ───
    police_stations:    List[PoliceStationInput] = []
