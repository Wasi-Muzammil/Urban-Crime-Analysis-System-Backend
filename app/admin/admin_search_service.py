from fastapi import HTTPException
from app.db.connection import get_connection


# ── Dropdown seeders ──────────────────────────────────────────────────────────

def get_locations_dropdown() -> dict:
    """
    Returns distinct (area_name, city, complete_location) pairs
    that have at least one incident.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                l.area_name,
                l.city,
                CONCAT(l.area_name, ', ', l.city) AS complete_location
            FROM Location l
            INNER JOIN Incident i ON l.location_id = i.location_id
            GROUP BY l.area_name, l.city
            ORDER BY l.city ASC, l.area_name ASC
            """
        )
        locations = cursor.fetchall()
        return {"total": len(locations), "locations": locations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch locations: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_categories_dropdown() -> dict:
    """
    Returns distinct category_name values that have at least one incident,
    sorted by most common first.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                category_name,
                COUNT(*) AS incident_count
            FROM Incident
            GROUP BY category_name
            ORDER BY incident_count DESC
            """
        )
        categories = cursor.fetchall()
        return {"total": len(categories), "categories": categories}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch categories: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_case_status_dropdown() -> dict:
    """
    Returns all CaseStatus ENUM values with their incident counts.
    Uses LEFT JOIN so all four statuses always appear even if count is 0.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                cs.status_name,
                COUNT(i.incident_id) AS incident_count
            FROM CaseStatus cs
            LEFT JOIN Incident i ON cs.status_id = i.status_id
            GROUP BY cs.status_name
            ORDER BY incident_count DESC
            """
        )
        statuses = cursor.fetchall()
        return {"total": len(statuses), "statuses": statuses}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch case statuses: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_police_station_dropdown() -> dict:
    """
    Returns distinct station_name values from the PoliceStation table
    that are actually linked to at least one incident.
    Duplicates eliminated via GROUP BY station_name.

    Response shape:
    {
      "total": 3,
      "stations": [
        {"station_name": "Gulshan Station"},
        {"station_name": "Clifton Station"},
        {"station_name": "Saddar Station"}
      ]
    }
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                ps.station_name,
                COUNT(ips.incident_id) AS incident_count
            FROM PoliceStation ps
            INNER JOIN Incident_PoliceStation ips ON ps.station_id = ips.station_id
            GROUP BY ps.station_name
            ORDER BY ps.station_name ASC
            """
        )
        stations = cursor.fetchall()
        return {"total": len(stations), "stations": stations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch police stations: {str(e)}")
    finally:
        cursor.close()
        conn.close()


# ── Admin search ──────────────────────────────────────────────────────────────

def admin_search_incidents(
    all_cases:       bool = False,
    location_wise:   bool = False,
    category_wise:   bool = False,
    status_wise:     bool = False,
    station_wise:    bool = False,
    area_name:       str  = None,
    city:            str  = None,
    category_name:   str  = None,
    status_name:     str  = None,
    station_name:    str  = None,
    limit:           int  = 20,
) -> dict:
    """
    Admin unified search. Handles all checkbox combination cases.
    Filters are built dynamically — any combination of the four filter
    checkboxes is supported via AND logic.

    ── Filter checkboxes ────────────────────────────────────────────────────
    all_cases        → overrides everything, returns all incidents
    location_wise    → requires area_name + city
    category_wise    → requires category_name
    status_wise      → requires status_name
    station_wise     → requires station_name

    ── All cases covered ────────────────────────────────────────────────────
    Single    : location | category | status | station
    Double    : location+category | location+status | location+station |
                category+status  | category+station | status+station
    Triple    : location+category+status | location+category+station |
                location+status+station  | category+status+station
    Quadruple : location+category+status+station
    Override  : all_cases (alone or combined with anything)
    ─────────────────────────────────────────────────────────────────────────
    """
    VALID_CATEGORIES = {"theft", "robbery", "assault", "homicide", "cybercrime", "fraud"}
    VALID_STATUSES   = {
        "Waiting",
        "Accepted; Under Investigation",
        "Investigated",
        "Rejected",
    }

    # ── Input validation ──────────────────────────────────────────────────────
    if category_name and category_name.lower() not in VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category_name. Must be one of: {', '.join(sorted(VALID_CATEGORIES))}"
        )
    if status_name and status_name not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status_name. Must be one of: {', '.join(VALID_STATUSES)}"
        )
    if limit < 1:
        raise HTTPException(status_code=422, detail="limit must be at least 1.")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # policestation_wise requires a JOIN that is not in the base SELECT —
    # we conditionally add it only when station_wise is active
    BASE_SELECT = """
        SELECT
            i.incident_id,
            i.title,
            i.category_name,
            i.description,
            i.crime_severity,
            i.incident_datetime,
            i.reported_at,
            l.area_name,
            l.street_address,
            l.city,
            l.postal_code,
            cs.status_name,
            v.name          AS victim_name,
            v.email         AS victim_email
        FROM Incident i
        JOIN Location        l   ON i.location_id = l.location_id
        JOIN CaseStatus      cs  ON i.status_id   = cs.status_id
        JOIN Incident_Victim iv  ON i.incident_id = iv.incident_id
        JOIN Victim          v   ON iv.victim_id  = v.victim_id
    """

    # Extra JOIN added only when policestation_wise is active
    STATION_JOIN = """
        JOIN Incident_PoliceStation ips ON i.incident_id = ips.incident_id
        JOIN PoliceStation          ps  ON ips.station_id = ps.station_id
    """

    try:
        # ── Case 1: all_cases overrides all filters ───────────────────────────
        if all_cases:
            cursor.execute(
                f"{BASE_SELECT} ORDER BY i.reported_at DESC LIMIT %s",
                (limit,)
            )
            incidents = cursor.fetchall()
            return {
                "active_filters": {"all_cases": True},
                "limit":          limit,
                "total":          len(incidents),
                "results":        incidents,
            }

        # ── Guard: at least one filter checkbox must be active ────────────────
        if not location_wise and not category_wise and not status_wise and not station_wise:
            raise HTTPException(
                status_code=422,
                detail=(
                    "At least one filter must be selected: "
                    "all_cases, location_wise, category_wise, "
                    "casestatus_wise, or policestation_wise."
                )
            )

        # ── Build WHERE clause dynamically ────────────────────────────────────
        conditions = []
        params     = []

        if location_wise:
            if not area_name or not city:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "area_name and city are required when location_wise is selected. "
                        "Use values from GET /admin/search/locations."
                    )
                )
            conditions.append("l.area_name = %s AND l.city = %s")
            params.extend([area_name, city])

        if category_wise:
            if not category_name:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "category_name is required when category_wise is selected. "
                        "Use values from GET /admin/search/categories."
                    )
                )
            conditions.append("i.category_name = %s")
            params.append(category_name.lower())

        if status_wise:
            if not status_name:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "status_name is required when casestatus_wise is selected. "
                        "Use values from GET /admin/search/case-status."
                    )
                )
            conditions.append("cs.status_name = %s")
            params.append(status_name)

        if station_wise:
            if not station_name:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "station_name is required when policestation_wise is selected. "
                        "Use values from GET /admin/search/police-station."
                    )
                )
            conditions.append("ps.station_name = %s")
            params.append(station_name)

        # Include STATION_JOIN only if policestation_wise is active
        join_clause  = STATION_JOIN if station_wise else ""
        where_clause = " AND ".join(conditions)
        params.append(limit)

        cursor.execute(
            f"{BASE_SELECT} {join_clause} WHERE {where_clause} "
            f"ORDER BY i.reported_at DESC LIMIT %s",
            tuple(params)
        )
        incidents = cursor.fetchall()

        # Build active_filters summary
        active_filters = {}
        if location_wise:
            active_filters["location_wise"]     = True
            active_filters["area_name"]         = area_name
            active_filters["city"]              = city
            active_filters["complete_location"] = f"{area_name}, {city}"
        if category_wise:
            active_filters["category_wise"]  = True
            active_filters["category_name"]  = category_name.lower()
        if status_wise:
            active_filters["casestatus_wise"] = True
            active_filters["status_name"]     = status_name
        if station_wise:
            active_filters["policestation_wise"] = True
            active_filters["station_name"]       = station_name

        return {
            "active_filters": active_filters,
            "limit":          limit,
            "total":          len(incidents),
            "results":        incidents,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Admin search failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()