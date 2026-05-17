from fastapi import HTTPException
from app.db.connection import get_connection
from app.admin.admin_schema import *
from typing import Optional
from app.core.logger import log_transaction
from datetime import datetime, timedelta

def get_all_viewers(admin_user: dict) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT
                user_id,
                email,
                name,
                DATE_FORMAT(created_at, '%d-%m-%Y') AS created_at
            FROM users
            WHERE role = 'viewer'
              AND user_id != %s
            ORDER BY created_at DESC
            """,
            (admin_user["user_id"],)
        )
        users = cursor.fetchall()
        return {"total": len(users), "users": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def delete_incident(
    target_user_id: int,
    incident_id:    int,
    admin_user:     dict,
    ip_address:     str = None,
) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT iv.user_id
            FROM Incident_Victim iv
            WHERE iv.incident_id = %s AND iv.user_id = %s
            """,
            (incident_id, target_user_id)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Incident {incident_id} not found for user {target_user_id}."
            )

        cursor.execute(
            """
            SELECT
                i.incident_id,
                i.location_id,
                i.status_id,
                cs.status_name
            FROM Incident i
            JOIN CaseStatus cs ON i.status_id = cs.status_id
            WHERE i.incident_id = %s
            """,
            (incident_id,)
        )
        incident = cursor.fetchone()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found.")

        if incident["status_name"] != "Rejected":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot delete incident {incident_id}. "
                    f"Current status is '{incident['status_name']}'. "
                    f"Only incidents with status 'Rejected' can be deleted."
                )
            )

        location_id = incident["location_id"]
        status_id   = incident["status_id"]

        cursor.execute(
            "SELECT suspect_id FROM Incident_Suspect WHERE incident_id = %s",
            (incident_id,)
        )
        suspect_ids = [r["suspect_id"] for r in cursor.fetchall()]

        cursor.execute(
            "SELECT station_id FROM Incident_PoliceStation WHERE incident_id = %s",
            (incident_id,)
        )
        station_ids = [r["station_id"] for r in cursor.fetchall()]

        cursor.execute("DELETE FROM Incident WHERE incident_id = %s", (incident_id,))

        for sid in suspect_ids:
            cursor.execute("DELETE FROM Suspect WHERE suspect_id = %s", (sid,))

        for station_id in station_ids:
            cursor.execute("DELETE FROM PoliceStation WHERE station_id = %s", (station_id,))

        cursor.execute("DELETE FROM CaseStatus WHERE status_id = %s", (status_id,))
        cursor.execute("DELETE FROM Location WHERE location_id = %s", (location_id,))

        conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Deletion failed and was rolled back: {str(e)}")
    finally:
        cursor.close()
        conn.close()

    admin_id = admin_user["user_id"]
    log_transaction(admin_id, "Incident",     "DELETE", incident_id, ip_address)
    log_transaction(admin_id, "Location",     "DELETE", location_id, ip_address)
    log_transaction(admin_id, "CaseStatus",   "DELETE", status_id,   ip_address)
    for sid in suspect_ids:
        log_transaction(admin_id, "Suspect",       "DELETE", sid,        ip_address)
    for station_id in station_ids:
        log_transaction(admin_id, "PoliceStation", "DELETE", station_id, ip_address)

    return {
        "message":          f"Incident {incident_id} deleted successfully.",
        "incident_id":      incident_id,
        "user_id":          target_user_id,
        "location_deleted": location_id,
        "status_deleted":   status_id,
        "suspects_deleted": len(suspect_ids),
        "stations_deleted": len(station_ids),
    }


def get_user_by_id(target_user_id: int, admin_user: dict) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT user_id, email, name
            FROM users
            WHERE user_id = %s AND role = 'viewer'
            """,
            (target_user_id,)
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with user_id {target_user_id} not found."
            )
        return user
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_victim_by_user_id(target_user_id: int) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT user_id, name, cnic, email, phone, address
            FROM Victim
            WHERE user_id = %s
            """,
            (target_user_id,)
        )
        victim = cursor.fetchone()
        if not victim:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No victim record found for user_id {target_user_id}. "
                    "This user may not have filed any incident report yet."
                )
            )
        return victim
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch victim info: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_user_incidents(target_user_id: int) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT user_id FROM Victim WHERE user_id = %s",
            (target_user_id,)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"No victim record found for user_id {target_user_id}."
            )

        cursor.execute(
            """
            SELECT
                i.incident_id,
                i.title,
                i.category_name,
                i.crime_severity,
                i.incident_datetime,
                i.reported_at,
                l.area_name,
                l.city,
                cs.status_name
            FROM Incident i
            JOIN Incident_Victim iv ON i.incident_id = iv.incident_id
            JOIN Location        l  ON i.location_id = l.location_id
            JOIN CaseStatus      cs ON i.status_id   = cs.status_id
            WHERE iv.user_id = %s
            ORDER BY i.reported_at DESC
            """,
            (target_user_id,)
        )
        incidents = cursor.fetchall()
        return {"user_id": target_user_id, "total": len(incidents), "incidents": incidents}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch incidents: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_user_incident_detail(target_user_id: int, incident_id: int) -> dict:
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT user_id FROM Incident_Victim
            WHERE incident_id = %s AND user_id = %s
            """,
            (incident_id, target_user_id)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Incident {incident_id} does not belong to user {target_user_id}."
            )

        cursor.execute(
            """
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
                l.street_address,
                l.city,
                l.postal_code,
                l.cctv_footage_path,
                cs.status_id,
                cs.status_name,
                v.user_id,
                v.name          AS victim_name,
                v.cnic          AS victim_cnic,
                v.email         AS victim_email,
                v.phone         AS victim_phone,
                v.address       AS victim_address,
                iv.injury_type
            FROM Incident i
            JOIN Location        l  ON i.location_id = l.location_id
            JOIN CaseStatus      cs ON i.status_id   = cs.status_id
            JOIN Incident_Victim iv ON i.incident_id = iv.incident_id
            JOIN Victim          v  ON iv.user_id    = v.user_id
            WHERE i.incident_id = %s AND iv.user_id = %s
            """,
            (incident_id, target_user_id)
        )
        incident = cursor.fetchone()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found.")

        cursor.execute(
            """
            SELECT
                s.suspect_id,
                s.name         AS suspect_name,
                s.cnic         AS suspect_cnic,
                s.status       AS suspect_status,
                s.picture_path AS suspect_picture,
                ins.arrest_date
            FROM Suspect s
            JOIN Incident_Suspect ins ON s.suspect_id = ins.suspect_id
            WHERE ins.incident_id = %s
            """,
            (incident_id,)
        )
        suspect = cursor.fetchone()

        cursor.execute(
            """
            SELECT
                ps.station_id,
                ps.station_name,
                ps.city               AS station_city,
                ps.address            AS station_address,
                ps.incharge_officer_name,
                ps.charges_filed
            FROM PoliceStation ps
            JOIN Incident_PoliceStation ips ON ps.station_id = ips.station_id
            WHERE ips.incident_id = %s
            """,
            (incident_id,)
        )
        stations = cursor.fetchall()

        return {
            "incident": {
                "incident_id":       incident["incident_id"],
                "title":             incident["title"],
                "category_name":     incident["category_name"],
                "description":       incident["description"],
                "crime_severity":    incident["crime_severity"],
                "incident_datetime": incident["incident_datetime"],
                "reported_at":       incident["reported_at"],
            },
            "location": {
                "location_id":       incident["location_id"],
                "area_name":         incident["area_name"],
                "street_address":    incident["street_address"],
                "city":              incident["city"],
                "postal_code":       incident["postal_code"],
                "cctv_footage_path": incident["cctv_footage_path"],
            },
            "case_status": {
                "status_id":   incident["status_id"],
                "status_name": incident["status_name"],
            },
            "victim": {
                "user_id":     incident["user_id"],
                "name":        incident["victim_name"],
                "cnic":        incident["victim_cnic"],
                "email":       incident["victim_email"],
                "phone":       incident["victim_phone"],
                "address":     incident["victim_address"],
                "injury_type": incident["injury_type"],
            },
            "suspect":         suspect if suspect else None,
            "police_stations": stations if stations else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch incident detail: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def validate_station_count(incident_id: int, count: int) -> dict:
    if count < 1:
        raise HTTPException(status_code=422, detail="Station count must be at least 1.")

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT i.crime_severity, l.city
            FROM Incident i
            JOIN Location l ON i.location_id = l.location_id
            WHERE i.incident_id = %s
            """,
            (incident_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found.")

        severity      = row["crime_severity"]
        incident_city = row["city"]

        if severity is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "crime_severity is not set for this incident. "
                    "Set crime_severity in the update form before requesting station count."
                )
            )

        if severity in ("Low", "Medium") and count != 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Incident severity is '{severity}'. "
                    f"Only exactly 1 police station is allowed for Low or Medium severity. "
                    f"You requested {count}."
                )
            )
        if severity == "High" and count < 2:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Incident severity is 'High'. "
                    f"At least 2 police stations are required for High severity incidents. "
                    f"You requested {count}."
                )
            )

        empty_slots = [
            {
                "slot":                  i + 1,
                "station_name":          "",
                "city":                  incident_city,
                "address":               "",
                "incharge_officer_name": "",
                "charges_filed":         0,
            }
            for i in range(count)
        ]

        return {
            "incident_id":    incident_id,
            "crime_severity": severity,
            "station_count":  count,
            "incident_city":  incident_city,
            "message":        f"Form updated. Please fill in {count} police station(s).",
            "station_slots":  empty_slots,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Station count validation failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def admin_update_incident(
    target_user_id: int,
    incident_id:    int,
    form:           AdminIncidentUpdateForm,
    admin_user:     dict,
    ip_address:     str = None,
) -> dict:
    VALID_SEVERITIES = {"Low", "Medium", "High"}
    VALID_CATEGORIES = {"theft", "robbery", "assault", "homicide", "cybercrime", "fraud"}
    VALID_STATUSES   = {
        "Arrested and confirmed criminal",
        "Not arrested but confirmed criminal",
        "Unconfirmed criminal- IN custody",
        "Unknown",
    }
    VALID_STATUS_NAMES = {
        "Waiting",
        "Accepted; Under Investigation",
        "Investigated",
        "Rejected",
    }

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # ── Ownership check ───────────────────────────────────────────────────
        cursor.execute(
            """
            SELECT user_id FROM Incident_Victim
            WHERE incident_id = %s AND user_id = %s
            """,
            (incident_id, target_user_id)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Incident {incident_id} does not belong to user {target_user_id}."
            )

        # ── Fetch current state including all NOT NULL columns ────────────────
        # FIX: fetch victim's current cnic/phone so we never send NULL
        # into NOT NULL columns when admin leaves those fields blank
        cursor.execute(
            """
            SELECT
                i.location_id,
                i.crime_severity,
                l.city      AS incident_city,
                v.cnic      AS current_cnic,
                v.phone     AS current_phone,
                v.address   AS current_address
            FROM Incident i
            JOIN Location        l  ON i.location_id = l.location_id
            JOIN Incident_Victim iv ON i.incident_id = iv.incident_id
            JOIN Victim          v  ON iv.user_id    = v.user_id
            WHERE i.incident_id = %s AND iv.user_id = %s
            """,
            (incident_id, target_user_id)
        )
        current       = cursor.fetchone()
        location_id   = current["location_id"]
        incident_city = current["incident_city"]

        # Resolve final values in Python — never pass None into NOT NULL columns
        final_severity = form.crime_severity if form.crime_severity else current["crime_severity"]
        final_cnic     = form.victim_cnic    if form.victim_cnic    else current["current_cnic"]
        final_phone    = form.victim_phone   if form.victim_phone   else current["current_phone"]
        final_address  = form.victim_address if form.victim_address else current["current_address"]

        # ── Validations ───────────────────────────────────────────────────────
        if form.crime_severity and form.crime_severity not in VALID_SEVERITIES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid crime_severity. Must be one of: {', '.join(VALID_SEVERITIES)}"
            )

        if form.status_name and form.status_name not in VALID_STATUS_NAMES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status_name. Must be one of: {', '.join(VALID_STATUS_NAMES)}"
            )

        if form.category_name and form.category_name.lower() not in VALID_CATEGORIES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid category_name. Must be one of: {', '.join(VALID_CATEGORIES)}"
            )

        if form.police_stations:
            station_count = len(form.police_stations)

            if final_severity in ("Low", "Medium") and station_count != 1:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Severity is '{final_severity}'. "
                        f"Exactly 1 police station required. You submitted {station_count}."
                    )
                )
            if final_severity == "High" and station_count < 2:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Severity is 'High'. "
                        f"At least 2 police stations required. You submitted {station_count}."
                    )
                )

            # City match — contains check in both directions
            invalid_stations = [
                ps.station_name
                for ps in form.police_stations
                if incident_city.strip().lower() not in ps.city.strip().lower()
                and ps.city.strip().lower() not in incident_city.strip().lower()
            ]
            if invalid_stations:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"All police stations must be from '{incident_city}'. "
                        f"Mismatched city in: {', '.join(invalid_stations)}"
                    )
                )

        # ── Update Incident ───────────────────────────────────────────────────
        cursor.execute(
            """
            UPDATE Incident SET
                title             = COALESCE(%s, title),
                category_name     = COALESCE(%s, category_name),
                incident_datetime = COALESCE(%s, incident_datetime),
                description       = COALESCE(%s, description),
                crime_severity    = COALESCE(%s, crime_severity)
            WHERE incident_id = %s
            """,
            (
                form.title,
                form.category_name,
                form.incident_datetime,
                form.description,
                form.crime_severity,
                incident_id,
            )
        )
        log_transaction(admin_user["user_id"], "Incident", "UPDATE", incident_id, ip_address)

        # ── Update Location ───────────────────────────────────────────────────
        cursor.execute(
            """
            UPDATE Location SET
                area_name         = COALESCE(%s, area_name),
                city              = COALESCE(%s, city),
                street_address    = COALESCE(%s, street_address),
                postal_code       = COALESCE(%s, postal_code),
                cctv_footage_path = COALESCE(%s, cctv_footage_path)
            WHERE location_id = %s
            """,
            (
                form.area_name,
                form.city,
                form.street_address,
                form.postal_code,
                form.cctv_footage_path,
                location_id,
            )
        )
        log_transaction(admin_user["user_id"], "Location", "UPDATE", location_id, ip_address)

        # ── Update CaseStatus ─────────────────────────────────────────────────
        cursor.execute(
            "SELECT status_id FROM Incident WHERE incident_id = %s",
            (incident_id,)
        )
        status_id = cursor.fetchone()["status_id"]

        if form.status_name is not None:
            cursor.execute(
                "UPDATE CaseStatus SET status_name = %s WHERE status_id = %s",
                (form.status_name, status_id)
            )
            log_transaction(admin_user["user_id"], "CaseStatus", "UPDATE", status_id, ip_address)

        # ── Update Victim ─────────────────────────────────────────────────────
        # FIX: use Python-resolved final values — never send None into
        # NOT NULL columns (cnic, phone). address is nullable so COALESCE is fine.
        cursor.execute(
            """
            UPDATE Victim SET
                cnic    = %s,
                phone   = %s,
                address = COALESCE(%s, address)
            WHERE user_id = %s
            """,
            (final_cnic, final_phone, final_address, target_user_id)
        )
        log_transaction(admin_user["user_id"], "Victim", "UPDATE", target_user_id, ip_address)

        # ── Update Incident_Victim ────────────────────────────────────────────
        if form.injury_type is not None:
            cursor.execute(
                """
                UPDATE Incident_Victim SET injury_type = %s
                WHERE incident_id = %s AND user_id = %s
                """,
                (form.injury_type, incident_id, target_user_id)
            )

        # ── Update or Insert Suspect ──────────────────────────────────────────
        if form.suspect:
            if form.suspect.status and form.suspect.status not in VALID_STATUSES:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid suspect status. Must be one of: {', '.join(VALID_STATUSES)}"
                )

            cursor.execute(
                "SELECT suspect_id FROM Incident_Suspect WHERE incident_id = %s",
                (incident_id,)
            )
            suspect_link = cursor.fetchone()

            if suspect_link:
                # ── Suspect exists → fetch current values, resolve in Python ──
                # FIX: same COALESCE NULL issue — fetch existing name/cnic first
                suspect_id = suspect_link["suspect_id"]
                cursor.execute(
                    "SELECT name, cnic, status FROM Suspect WHERE suspect_id = %s",
                    (suspect_id,)
                )
                cur_sus = cursor.fetchone()

                final_sus_name   = form.suspect.name   if form.suspect.name   else cur_sus["name"]
                final_sus_cnic   = form.suspect.cnic   if form.suspect.cnic   else cur_sus["cnic"]
                final_sus_status = form.suspect.status if form.suspect.status else cur_sus["status"]

                cursor.execute(
                    """
                    UPDATE Suspect SET
                        name   = %s,
                        cnic   = %s,
                        status = %s
                    WHERE suspect_id = %s
                    """,
                    (final_sus_name, final_sus_cnic, final_sus_status, suspect_id)
                )
                if form.suspect.arrest_date:
                    cursor.execute(
                        """
                        UPDATE Incident_Suspect SET arrest_date = %s
                        WHERE incident_id = %s AND suspect_id = %s
                        """,
                        (form.suspect.arrest_date, incident_id, suspect_id)
                    )
                log_transaction(admin_user["user_id"], "Suspect", "UPDATE", suspect_id, ip_address)

            else:
                # ── No suspect yet → INSERT with safe fallbacks for NOT NULL ──
                if not form.suspect.status:
                    raise HTTPException(
                        status_code=422,
                        detail="Suspect status is required when adding a new suspect."
                    )

                ins_name   = form.suspect.name.strip() if form.suspect.name and form.suspect.name.strip() else "Unknown"
                ins_cnic   = form.suspect.cnic.strip() if form.suspect.cnic and form.suspect.cnic.strip() else "Unknown"
                ins_status = form.suspect.status.strip()

                cursor.execute(
                    "INSERT INTO Suspect (name, cnic, status) VALUES (%s, %s, %s)",
                    (ins_name, ins_cnic, ins_status)
                )
                new_suspect_id = cursor.lastrowid
                cursor.execute(
                    """
                    INSERT INTO Incident_Suspect (incident_id, suspect_id, arrest_date)
                    VALUES (%s, %s, %s)
                    """,
                    (incident_id, new_suspect_id, form.suspect.arrest_date)
                )
                log_transaction(admin_user["user_id"], "Suspect",          "INSERT", new_suspect_id, ip_address)
                log_transaction(admin_user["user_id"], "Incident_Suspect", "INSERT", incident_id,    ip_address)

        # ── Replace Police Stations ───────────────────────────────────────────
        if form.police_stations:
            cursor.execute(
                "SELECT station_id FROM Incident_PoliceStation WHERE incident_id = %s",
                (incident_id,)
            )
            existing_ids = [r["station_id"] for r in cursor.fetchall()]

            cursor.execute(
                "DELETE FROM Incident_PoliceStation WHERE incident_id = %s",
                (incident_id,)
            )
            for sid in existing_ids:
                cursor.execute("DELETE FROM PoliceStation WHERE station_id = %s", (sid,))
                log_transaction(admin_user["user_id"], "PoliceStation", "DELETE", sid, ip_address)

            for ps in form.police_stations:
                cursor.execute(
                    """
                    INSERT INTO PoliceStation
                        (station_name, city, address, incharge_officer_name, charges_filed)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (ps.station_name, ps.city, ps.address, ps.incharge_officer_name, ps.charges_filed)
                )
                new_sid = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO Incident_PoliceStation (incident_id, station_id) VALUES (%s, %s)",
                    (incident_id, new_sid)
                )
                log_transaction(admin_user["user_id"], "PoliceStation",          "INSERT", new_sid,     ip_address)
                log_transaction(admin_user["user_id"], "Incident_PoliceStation", "INSERT", incident_id, ip_address)

        conn.commit()

        return {
            "message":     "Incident updated successfully.",
            "incident_id": incident_id,
            "user_id":     target_user_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed and was rolled back: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_user_transaction_logs(
    target_user_id: int,
    action_type:    Optional[str] = None,
    from_date:      Optional[str] = None,
    to_date:        Optional[str] = None,
) -> dict:
    VALID_ACTION_TYPES = {"INSERT", "UPDATE", "DELETE"}

    if action_type and action_type.upper() not in VALID_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Invalid action_type. Must be one of: INSERT, UPDATE, DELETE"
        )

    now = datetime.now()

    if not from_date and not to_date:
        resolved_from   = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = "Default range: last 24 hours"
    elif from_date and not to_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid from_date. Use YYYY-MM-DD.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = f"From {from_date} until now"
    elif not from_date and to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid to_date. Use YYYY-MM-DD.")
        resolved_from   = "2000-01-01 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"All records until end of {to_date}"
    else:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
            datetime.strptime(to_date,   "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date cannot be later than to_date.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"From {from_date} to {to_date} (inclusive)"

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT user_id, email, name FROM users WHERE user_id = %s",
            (target_user_id,)
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with user_id {target_user_id} not found."
            )

        conditions = ["user_id = %s", "logged_at >= %s", "logged_at <= %s"]
        params     = [target_user_id, resolved_from, resolved_to]

        if action_type:
            conditions.append("action_type = %s")
            params.append(action_type.upper())

        where_clause = " AND ".join(conditions)

        cursor.execute(
            f"""
            SELECT transaction_id, user_id, table_name, action_type,
                   record_id, ip_address, logged_at
            FROM `Transaction`
            WHERE {where_clause}
            ORDER BY logged_at DESC
            """,
            tuple(params)
        )
        rows = cursor.fetchall()

        logs = [
            {
                "transaction_id": row["transaction_id"],
                "action_type":    row["action_type"],
                "table_name":     row["table_name"],
                "record_id":      row["record_id"],
                "ip_address":     row["ip_address"],
                "logged_at":      row["logged_at"].strftime("%d-%m-%Y %H:%M:%S") if row["logged_at"] else None,
            }
            for row in rows
        ]

        return {
            "user_id":    target_user_id,
            "user_email": user["email"],
            "user_name":  user["name"],
            "filters_applied": {
                "action_type":     action_type.upper() if action_type else "ALL",
                "from":            resolved_from,
                "to":              resolved_to,
                "date_range_note": date_range_note,
            },
            "total": len(logs),
            "logs":  logs,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch transaction logs: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_user_audit_logs(
    target_user_id: int,
    event_type:     Optional[str] = None,
    from_date:      Optional[str] = None,
    to_date:        Optional[str] = None,
) -> dict:
    VALID_EVENT_TYPES = {"LOGIN", "LOGOUT", "ADMIN_ACTION", "ROLE_CHANGE"}

    if event_type and event_type.upper() not in VALID_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail="Invalid event_type. Must be one of: LOGIN, LOGOUT, ADMIN_ACTION, ROLE_CHANGE"
        )

    now = datetime.now()

    if not from_date and not to_date:
        resolved_from   = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = "Default range: last 24 hours"
    elif from_date and not to_date:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid from_date. Use YYYY-MM-DD.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = now.strftime("%Y-%m-%d %H:%M:%S")
        date_range_note = f"From {from_date} until now"
    elif not from_date and to_date:
        try:
            datetime.strptime(to_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid to_date. Use YYYY-MM-DD.")
        resolved_from   = "2000-01-01 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"All records until end of {to_date}"
    else:
        try:
            datetime.strptime(from_date, "%Y-%m-%d")
            datetime.strptime(to_date,   "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD.")
        if from_date > to_date:
            raise HTTPException(status_code=422, detail="from_date cannot be later than to_date.")
        resolved_from   = f"{from_date} 00:00:00"
        resolved_to     = f"{to_date} 23:59:59"
        date_range_note = f"From {from_date} to {to_date} (inclusive)"

    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT user_id, email, name FROM users WHERE user_id = %s",
            (target_user_id,)
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"User with user_id {target_user_id} not found."
            )

        conditions = ["user_id = %s", "logged_at >= %s", "logged_at <= %s"]
        params     = [target_user_id, resolved_from, resolved_to]

        if event_type:
            conditions.append("event_type = %s")
            params.append(event_type.upper())

        where_clause = " AND ".join(conditions)

        cursor.execute(
            f"""
            SELECT audit_id, user_id, event_type, description, ip_address, logged_at
            FROM `Audit`
            WHERE {where_clause}
            ORDER BY logged_at DESC
            """,
            tuple(params)
        )
        rows = cursor.fetchall()

        logs = [
            {
                "audit_id":    row["audit_id"],
                "event_type":  row["event_type"],
                "description": row["description"],
                "ip_address":  row["ip_address"],
                "logged_at":   row["logged_at"].strftime("%d-%m-%Y %H:%M:%S") if row["logged_at"] else None,
            }
            for row in rows
        ]

        return {
            "user_id":    target_user_id,
            "user_email": user["email"],
            "user_name":  user["name"],
            "filters_applied": {
                "event_type":      event_type.upper() if event_type else "ALL",
                "from":            resolved_from,
                "to":              resolved_to,
                "date_range_note": date_range_note,
            },
            "total": len(logs),
            "logs":  logs,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch audit logs: {str(e)}")
    finally:
        cursor.close()
        conn.close()