from typing import List, Optional
from pydantic import BaseModel


class PoliceStationInput(BaseModel):
    station_name:          str
    city:                  str
    address:               str
    incharge_officer_name: str
    charges_filed:         int = 0


class SuspectUpdateInput(BaseModel):
    name:        Optional[str] = None
    cnic:        Optional[str] = None
    status:      Optional[str] = None   # ← FIXED: was `str` (required)
    arrest_date: Optional[str] = None


class AdminIncidentUpdateForm(BaseModel):
    title:             Optional[str] = None
    category_name:     Optional[str] = None
    incident_datetime: Optional[str] = None
    description:       Optional[str] = None
    crime_severity:    Optional[str] = None
    status_name:       Optional[str] = None
    area_name:         Optional[str] = None
    city:              Optional[str] = None
    street_address:    Optional[str] = None
    postal_code:       Optional[str] = None
    cctv_footage_path: Optional[str] = None
    victim_cnic:       Optional[str] = None
    victim_phone:      Optional[str] = None
    victim_address:    Optional[str] = None
    injury_type:       Optional[str] = None
    suspect:           Optional[SuspectUpdateInput] = None
    police_stations:   List[PoliceStationInput] = []