from fastapi import HTTPException
from app.db.connection import get_connection


def get_all_locations_for_dropdown() -> dict:
    """
    Seeds the location dropdown.
    Returns distinct (area_name, city) pairs that have at least one incident.
    GROUP BY guarantees no duplicate complete_location entries.
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


def get_all_categories_for_dropdown() -> dict:
    """
    Seeds the category dropdown.
    Returns only categories that have at least one incident, most common first.
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


def search_incidents(
    all_cases:     bool = False,
    location_wise: bool = False,
    category_wise: bool = False,
    area_name:     str  = None,
    city:          str  = None,
    category_name: str  = None,
) -> dict:
    """
    Unified search function handling all four checkbox combination cases.

    ── Case logic ───────────────────────────────────────────────────────────
    Case 1 │ all_cases=True (alone or with anything else)
           │ → Return ALL incidents, ignore all filters
           │ Also applies when all three checkboxes are checked simultaneously
           │
    Case 2 │ location_wise=True only
           │ → Filter by area_name + city, ignore category
           │ → Requires area_name and city from location dropdown
           │
    Case 3 │ category_wise=True only
           │ → Filter by category_name, ignore location
           │ → Requires category_name from category dropdown
           │
    Case 4 │ location_wise=True AND category_wise=True (no all_cases)
           │ → Filter by BOTH area_name + city AND category_name
           │ → Requires area_name, city AND category_name
    ────────────────────────────────────────────────────────────────────────

    Values for area_name, city, category_name must come from the dropdown
    endpoints (/search/locations and /search/categories) — they are exact
    match values, not free-text search inputs.
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Base SELECT used in every case — joins Location and CaseStatus
    BASE_SELECT = """
        SELECT
            i.incident_id,
            i.title,
            i.category_name,
            i.description,
            i.crime_severity,
            i.incident_datetime,
            i.reported_at,
            l.location_id,
            l.area_name,
            l.city,
            l.street_address,
            l.postal_code,
            cs.status_name
        FROM Incident i
        JOIN Location   l  ON i.location_id = l.location_id
        JOIN CaseStatus cs ON i.status_id   = cs.status_id
    """

    try:
        # ── Case 1: all_cases checked (or all three checked) ──────────────────
        # all_cases overrides everything — return every incident unconditionally
        if all_cases:
            cursor.execute(f"{BASE_SELECT} ORDER BY i.reported_at DESC LIMIT 10")
            incidents = cursor.fetchall()
            return {
                "active_filters": {"all_cases": True},
                "total":          len(incidents),
                "results":        incidents,
            }

        # ── Validate that at least one filter checkbox is checked ─────────────
        if not location_wise and not category_wise:
            raise HTTPException(
                status_code=422,
                detail=(
                    "At least one filter must be selected: "
                    "all_cases, location_wise, or category_wise."
                )
            )

        # ── Case 2: location_wise only ────────────────────────────────────────
        if location_wise and not category_wise:
            if not area_name or not city:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "area_name and city are required when location_wise is selected. "
                        "Use values from GET /search/locations."
                    )
                )
            cursor.execute(
                f"""
                {BASE_SELECT}
                WHERE l.area_name = %s AND l.city = %s
                ORDER BY i.reported_at DESC LIMIT 10
                """,
                (area_name, city)
            )
            incidents = cursor.fetchall()
            return {
                "active_filters": {
                    "location_wise":    True,
                    "area_name":        area_name,
                    "city":             city,
                    "complete_location": f"{area_name}, {city}",
                },
                "total":   len(incidents),
                "results": incidents,
            }

        # ── Case 3: category_wise only ────────────────────────────────────────
        if category_wise and not location_wise:
            if not category_name:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "category_name is required when category_wise is selected. "
                        "Use values from GET /search/categories."
                    )
                )
            VALID = {"theft", "robbery", "assault", "homicide", "cybercrime", "fraud"}
            if category_name.lower() not in VALID:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid category_name. Must be one of: {', '.join(sorted(VALID))}"
                )
            cursor.execute(
                f"""
                {BASE_SELECT}
                WHERE i.category_name = %s
                ORDER BY i.reported_at DESC LIMIT 10
                """,
                (category_name.lower(),)
            )
            incidents = cursor.fetchall()
            return {
                "active_filters": {
                    "category_wise": True,
                    "category_name": category_name.lower(),
                },
                "total":   len(incidents),
                "limit": 10,
                "results": incidents,
            }

        # ── Case 4: location_wise AND category_wise both checked ──────────────
        if location_wise and category_wise:
            if not area_name or not city:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "area_name and city are required when location_wise is selected. "
                        "Use values from GET /search/locations."
                    )
                )
            if not category_name:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "category_name is required when category_wise is selected. "
                        "Use values from GET /search/categories."
                    )
                )
            VALID = {"theft", "robbery", "assault", "homicide", "cybercrime", "fraud"}
            if category_name.lower() not in VALID:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid category_name. Must be one of: {', '.join(sorted(VALID))}"
                )
            cursor.execute(
                f"""
                {BASE_SELECT}
                WHERE l.area_name     = %s
                  AND l.city          = %s
                  AND i.category_name = %s
                ORDER BY i.reported_at DESC LIMIT 10
                """,
                (area_name, city, category_name.lower())
            )
            incidents = cursor.fetchall()
            return {
                "active_filters": {
                    "location_wise":     True,
                    "category_wise":     True,
                    "area_name":         area_name,
                    "city":              city,
                    "complete_location": f"{area_name}, {city}",
                    "category_name":     category_name.lower(),
                },
                "total":   len(incidents),
                "results": incidents,
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()