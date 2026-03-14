from fastapi import APIRouter, Depends, Query, Header, HTTPException
from typing import Optional
from app.core.security import require_admin
from app.admin.admin_search_service import (
    get_locations_dropdown,
    get_categories_dropdown,
    get_case_status_dropdown,
    get_police_station_dropdown,
    admin_search_incidents,
)

router = APIRouter()


# ── Dropdown seeders ──────────────────────────────────────────────────────────

@router.get("/search/locations")
def fetch_locations(current_user: dict = Depends(require_admin)):
    """
    Admin-only. Seeds the location dropdown when location_wise is checked.
    Returns distinct (area_name, city, complete_location) pairs.
    """
    return get_locations_dropdown()


@router.get("/search/categories")
def fetch_categories(current_user: dict = Depends(require_admin)):
    """
    Admin-only. Seeds the category dropdown when category_wise is checked.
    Returns categories with incident counts, most common first.
    """
    return get_categories_dropdown()


@router.get("/search/case-status")
def fetch_case_statuses(current_user: dict = Depends(require_admin)):
    """
    Admin-only. Seeds the case status dropdown when casestatus_wise is checked.
    Returns all four CaseStatus ENUM values with their incident counts.

    Response:
    {
      "total": 4,
      "statuses": [
        {"status_name": "Waiting",                      "incident_count": 8},
        {"status_name": "Accepted; Under Investigation", "incident_count": 4},
        {"status_name": "Investigated",                 "incident_count": 2},
        {"status_name": "Rejected",                     "incident_count": 1}
      ]
    }
    """
    return get_case_status_dropdown()


@router.get("/search/police-station")
def fetch_police_stations(current_user: dict = Depends(require_admin)):
    """
    Admin-only. Seeds the police station dropdown when policestation_wise
    is checked. Returns distinct station_name values from PoliceStation
    table that are linked to at least one incident.
    Duplicate station_names eliminated via GROUP BY.

    Response:
    {
      "total": 3,
      "stations": [
        {"station_name": "Clifton Station",  "incident_count": 3},
        {"station_name": "Gulshan Station",  "incident_count": 2},
        {"station_name": "Saddar Station",   "incident_count": 1}
      ]
    }
    """
    return get_police_station_dropdown()


# ── Main admin search endpoint ────────────────────────────────────────────────

@router.get("/search/incidents")
def admin_search(

    # ── Checkbox states ───────────────────────────────────────────────────────
    all_cases: bool = Query(
        False,
        description="Returns ALL incidents. Overrides all other filters when True."
    ),
    location_wise: bool = Query(
        False,
        description="Filter by location. Requires area_name and city."
    ),
    category_wise: bool = Query(
        False,
        description="Filter by crime category. Requires category_name."
    ),
    casestatus_wise: bool = Query(
        False,
        description="Filter by case status. Requires status_name."
    ),
    policestation_wise: bool = Query(
        False,
        description="Filter by police station. Requires station_name."
    ),

    # ── Filter values from dropdowns ──────────────────────────────────────────
    area_name: Optional[str] = Query(
        None,
        description="Required when location_wise=true. From GET /admin/search/locations."
    ),
    city: Optional[str] = Query(
        None,
        description="Required when location_wise=true. From GET /admin/search/locations."
    ),
    category_name: Optional[str] = Query(
        None,
        description="Required when category_wise=true. From GET /admin/search/categories."
    ),
    status_name: Optional[str] = Query(
        None,
        description="Required when casestatus_wise=true. From GET /admin/search/case-status."
    ),
    station_name: Optional[str] = Query(
        None,
        description="Required when policestation_wise=true. From GET /admin/search/police-station."
    ),

    # ── Limit ─────────────────────────────────────────────────────────────────
    limit: int = Query(
        20,
        ge=1,
        description="Max records to return. Default 20. Admin sets any value."
    ),

    # ── Debounce ──────────────────────────────────────────────────────────────
    request_id: Optional[str] = Header(
        None,
        alias="X-Request-ID",
        description="Echoed back in response for frontend debounce handling."
    ),

    current_user: dict = Depends(require_admin),
):
    """
    Admin-only unified incident search with five simultaneous filter options.

    ── Single filter cases ──────────────────────────────────────────────────
    all_cases only:
      GET /admin/search/incidents?all_cases=true&limit=50

    location_wise only:
      GET /admin/search/incidents?location_wise=true&area_name=Gulshan&city=Karachi

    category_wise only:
      GET /admin/search/incidents?category_wise=true&category_name=robbery

    casestatus_wise only:
      GET /admin/search/incidents?casestatus_wise=true&status_name=Waiting

    policestation_wise only:
      GET /admin/search/incidents?policestation_wise=true&station_name=Gulshan Station

    ── Double filter cases ───────────────────────────────────────────────────
    location + category:
      ?location_wise=true&area_name=Gulshan&city=Karachi&category_wise=true&category_name=robbery

    location + status:
      ?location_wise=true&area_name=Gulshan&city=Karachi&casestatus_wise=true&status_name=Waiting

    location + station:
      ?location_wise=true&area_name=Gulshan&city=Karachi&policestation_wise=true&station_name=Gulshan Station

    category + status:
      ?category_wise=true&category_name=robbery&casestatus_wise=true&status_name=Rejected

    category + station:
      ?category_wise=true&category_name=robbery&policestation_wise=true&station_name=Gulshan Station

    status + station:
      ?casestatus_wise=true&status_name=Waiting&policestation_wise=true&station_name=Saddar Station

    ── Triple filter cases ───────────────────────────────────────────────────
    location + category + status:
      ?location_wise=true&area_name=Gulshan&city=Karachi
      &category_wise=true&category_name=robbery
      &casestatus_wise=true&status_name=Waiting

    location + category + station:
      ?location_wise=true&area_name=Gulshan&city=Karachi
      &category_wise=true&category_name=robbery
      &policestation_wise=true&station_name=Gulshan Station

    location + status + station:
      ?location_wise=true&area_name=Gulshan&city=Karachi
      &casestatus_wise=true&status_name=Waiting
      &policestation_wise=true&station_name=Gulshan Station

    category + status + station:
      ?category_wise=true&category_name=robbery
      &casestatus_wise=true&status_name=Waiting
      &policestation_wise=true&station_name=Gulshan Station

    ── Quadruple filter ─────────────────────────────────────────────────────
    location + category + status + station (all four simultaneously):
      ?location_wise=true&area_name=Gulshan&city=Karachi
      &category_wise=true&category_name=robbery
      &casestatus_wise=true&status_name=Waiting
      &policestation_wise=true&station_name=Gulshan Station

    ── all_cases override ────────────────────────────────────────────────────
    Checking all_cases alone or with any other combination always returns
    every incident regardless of other params.
    """
    if not all_cases and not location_wise and not category_wise \
            and not casestatus_wise and not policestation_wise:
        raise HTTPException(
            status_code=422,
            detail=(
                "At least one checkbox must be selected: "
                "all_cases, location_wise, category_wise, "
                "casestatus_wise, or policestation_wise."
            )
        )

    result = admin_search_incidents(
        all_cases     = all_cases,
        location_wise = location_wise,
        category_wise = category_wise,
        status_wise   = casestatus_wise,
        station_wise  = policestation_wise,
        area_name     = area_name,
        city          = city,
        category_name = category_name,
        status_name   = status_name,
        station_name  = station_name,
        limit         = limit,
    )

    result["request_id"] = request_id
    return result