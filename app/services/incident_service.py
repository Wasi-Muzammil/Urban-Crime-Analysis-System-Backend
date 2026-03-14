from fastapi import HTTPException
from app.db.connection import get_connection
from app.models.incident import CrimeReportForm, MediaUpdateForm
from app.core.logger import log_transaction 


def submit_crime_report(
    form:         CrimeReportForm,
    current_user: dict,
    ip_address:   str = None,
) -> dict:
    """
    Crime Application Form submission.

    Transaction order (single DB transaction — all or nothing):
      1. INSERT into Location        (cctv_footage_path optional)
      2. INSERT into CaseStatus      (hardcoded 'Waiting')
      3. INSERT into Incident        (crime_severity NULL — admin sets later)
      4. INSERT into Victim          (victim_id = user_id from JWT)
      5. INSERT into Incident_Victim
      6. INSERT into Suspect         (ONLY if victim provided picture_path)
         └── INSERT into Incident_Suspect  (links suspect to incident)

    Step 6 creates a partial/placeholder Suspect row with:
      - picture_path  → uploaded by victim
      - name          → 'Unknown' (admin fills real name later)
      - cnic          → 'Unknown' (admin fills real CNIC later)
      - status        → 'Suspected' (default, admin updates after review)

    Transaction logs written after successful commit.

    REQUIRED: title, category_name, incident_datetime,
              area_name, city, victim_cnic, victim_phone
    OPTIONAL: description, street_address, postal_code,
              cctv_footage_path, picture_path (suspect photo),
              victim_address, injury_type
    ADMIN-ONLY: crime_severity, suspect name/cnic/status
    AUTO-HANDLED: reported_at, status='Waiting',
                  victim_name + email from JWT
    """
    conn   = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # ── 1. Insert Location ────────────────────────────────────────────────
        cursor.execute(
            """INSERT INTO Location
                   (area_name, street_address, postal_code, city, cctv_footage_path)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                form.area_name,
                form.street_address,        # optional
                form.postal_code,           # optional
                form.city,
                form.cctv_footage_path,     # optional
            )
        )
        location_id = cursor.lastrowid

        # ── 2. Insert CaseStatus as 'Waiting' ────────────────────────────────
        cursor.execute("INSERT INTO CaseStatus (status_name) VALUES ('Waiting')")
        status_id = cursor.lastrowid

        # ── 3. Insert Incident ────────────────────────────────────────────────
        # crime_severity excluded — stays NULL until admin sets it
        cursor.execute(
            """INSERT INTO Incident
                   (title, category_name, incident_datetime, description,
                    location_id, status_id)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                form.title,
                form.category_name,
                form.incident_datetime,
                form.description,           # optional
                location_id,
                status_id,
            )
        )
        incident_id = cursor.lastrowid

        # ── 4. Insert Victim ──────────────────────────────────────────────────
        victim_id = current_user["user_id"]
        cursor.execute(
            """INSERT INTO Victim (victim_id, user_id, name, cnic, email, phone, address)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                   name    = VALUES(name),
                   cnic    = VALUES(cnic),
                   email   = VALUES(email),
                   phone   = VALUES(phone),
                   address = VALUES(address)""",
            (
                victim_id,
                victim_id,
                current_user["name"],       # from Google OAuth
                form.victim_cnic,
                current_user["email"],      # from Google OAuth
                form.victim_phone,
                form.victim_address,        # optional
            )
        )

        # ── 5. Insert Incident_Victim junction ────────────────────────────────
        cursor.execute(
            """INSERT INTO Incident_Victim (incident_id, victim_id, injury_type)
               VALUES (%s, %s, %s)""",
            (incident_id, victim_id, form.injury_type)  # injury_type optional
        )

        # ── 6. Insert partial Suspect if victim provided a picture ────────────
        # Victim only knows what the suspect looks like (picture), not their
        # identity. We create a placeholder row so the picture is stored and
        # linked. Admin later fills in name, cnic, and updates status.
        suspect_id = None
        if form.picture_path:
            cursor.execute(
                """INSERT INTO Suspect (name, cnic, status, picture_path)
                   VALUES ('Unknown', 'Unknown', 'Unknown', %s)""",
                (form.picture_path,)
            )
            suspect_id = cursor.lastrowid

            # Link the suspect placeholder to this incident
            cursor.execute(
                """INSERT INTO Incident_Suspect (incident_id, suspect_id)
                   VALUES (%s, %s)""",
                (incident_id, suspect_id)
            )

        # ── Commit all inserts atomically ─────────────────────────────────────
        conn.commit()

    except Exception as e:
        conn.rollback()     # undo ALL inserts if anything fails
        raise HTTPException(
            status_code=500,
            detail=f"Transaction failed and was rolled back: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

    # ── Write transaction logs AFTER successful commit ────────────────────────
    user_id = current_user["user_id"]
    log_transaction(user_id, "Location",        "INSERT", location_id, ip_address)
    log_transaction(user_id, "CaseStatus",      "INSERT", status_id,   ip_address)
    log_transaction(user_id, "Incident",        "INSERT", incident_id, ip_address)
    log_transaction(user_id, "Victim",          "INSERT", victim_id,   ip_address)
    log_transaction(user_id, "Incident_Victim", "INSERT", incident_id, ip_address)
    if suspect_id:
        log_transaction(user_id, "Suspect",         "INSERT", suspect_id,  ip_address)
        log_transaction(user_id, "Incident_Suspect","INSERT", incident_id, ip_address)

    return {
        "message":           "Crime report submitted successfully.",
        "incident_id":       incident_id,
        "location_id":       location_id,
        "status":            "Waiting",
        "crime_severity":    "Pending — admin will review and set this.",
        "victim_id":         victim_id,
        "suspect_created":   suspect_id is not None,
        "suspect_id":        suspect_id,  # None if no picture was provided
    }


def update_incident_media(
    incident_id:  int,
    form:         MediaUpdateForm,
    current_user: dict,
    ip_address:   str = None,
) -> dict:
    """
    Victim updates CCTV footage paths for their incident's location.

    Replaces ALL existing Location_CCTV rows for that location
    with the new list provided. Ownership verified first.
    Transaction log written on success.
    """
    if not form.cctv_footage_path:
        raise HTTPException(
            status_code=422,
            detail="cctv_footage_path must contain one path."
        )

    victim_id = current_user["user_id"]
    conn      = get_connection()
    cursor    = conn.cursor(dictionary=True)

    try:
        # ── Ownership check ───────────────────────────────────────────────────
        cursor.execute(
            """SELECT victim_id FROM Incident_Victim
               WHERE incident_id = %s AND victim_id = %s""",
            (incident_id, victim_id)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to update this incident."
            )

        # ── Get location_id ───────────────────────────────────────────────────
        cursor.execute(
            "SELECT location_id FROM Incident WHERE incident_id = %s",
            (incident_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Incident not found.")
        location_id = row["location_id"]

        if form.cctv_footage_path:
            cursor.execute(
                "UPDATE Location SET cctv_footage_path = %s WHERE location_id = %s",
                (form.cctv_footage_path, location_id)
            )
        if form.picture_path:
            cursor.execute(
                "UPDATE Location SET picture_path = %s WHERE location_id = %s",
                (form.picture_path, location_id)
            )

        conn.commit()

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
    finally:
        cursor.close()
        conn.close()

    # Transaction logs
    log_transaction(current_user["user_id"], "Location", "UPDATE", location_id, ip_address)

    return {
        "message":          "CCTV footage path updated successfully.",
        "incident_id":       incident_id,
        "location_id":       location_id,
        "cctv_footage_path": form.cctv_footage_path,
    }


def get_my_incidents(current_user: dict) -> dict:
    """
    Returns all incidents filed by the logged-in victim.
    Read-only — no transaction log needed.
    """
    victim_id = current_user["user_id"]
    conn      = get_connection()
    cursor    = conn.cursor(dictionary=True)

    try:
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
                l.postal_code,
                l.city,
                l.cctv_footage_path,
                cs.status_id,
                cs.status_name,
                iv.injury_type
            FROM Incident i
            JOIN Incident_Victim iv ON i.incident_id = iv.incident_id
            JOIN Location        l  ON i.location_id = l.location_id
            JOIN CaseStatus      cs ON i.status_id   = cs.status_id
            WHERE iv.victim_id = %s
            ORDER BY i.reported_at DESC
            """,
            (victim_id,)
        )
        incidents = cursor.fetchall()

        if not incidents:
            return {"message": "No incident reports found.", "total": 0, "incidents": []}

        return {"total": len(incidents), "incidents": incidents}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch incidents: {str(e)}")
    finally:
        cursor.close()
        conn.close()


def get_incident_detail(incident_id: int, current_user: dict) -> dict:
    """
    Full detail of one incident for the logged-in victim.
    Ownership verified before any data is returned.

    Returns data from:
      Incident, Location, Location_CCTV, CaseStatus,
      Victim, Incident_Victim, Suspect, Incident_Suspect,
      PoliceStation, Incident_PoliceStation
    """
    victim_id = current_user["user_id"]
    conn      = get_connection()
    cursor    = conn.cursor(dictionary=True)

    try:
        # ── Ownership check ───────────────────────────────────────────────────
        cursor.execute(
            """SELECT victim_id FROM Incident_Victim
               WHERE incident_id = %s AND victim_id = %s""",
            (incident_id, victim_id)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to view this incident."
            )

        # ── Core incident + location + case status + victim ───────────────────
        cursor.execute(
            """
            SELECT
                i.incident_id,      i.title,          i.category_name,
                i.description,      i.crime_severity,
                i.incident_datetime, i.reported_at,
                l.location_id,      l.area_name,      l.street_address,
                l.postal_code,      l.city,   l.cctv_footage_path,
                cs.status_id,       cs.status_name,   cs.phone AS status_phone,
                v.victim_id,        v.name  AS victim_name,
                v.cnic  AS victim_cnic,  v.email AS victim_email,
                v.phone AS victim_phone, v.address AS victim_address,
                iv.injury_type
            FROM Incident i
            JOIN Location        l  ON i.location_id = l.location_id
            JOIN CaseStatus      cs ON i.status_id   = cs.status_id
            JOIN Incident_Victim iv ON i.incident_id = iv.incident_id
            JOIN Victim          v  ON iv.victim_id  = v.victim_id
            WHERE i.incident_id = %s AND iv.victim_id = %s
            """,
            (incident_id, victim_id)
        )
        incident = cursor.fetchone()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found.")

        # ── Suspects linked to this incident ──────────────────────────────────
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
        suspects = cursor.fetchall()

        # ── Police stations linked to this incident ───────────────────────────
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
                "crime_severity":    incident["crime_severity"],  # NULL until admin sets
                "incident_datetime": incident["incident_datetime"],
                "reported_at":       incident["reported_at"],
            },
            "location": {
                "location_id":       incident["location_id"],
                "area_name":         incident["area_name"],
                "street_address":    incident["street_address"],
                "postal_code":       incident["postal_code"],
                "city":              incident["city"],
                "cctv_footage_path": incident["cctv_footage_path"],
            },
            "case_status": {
                "status_id":   incident["status_id"],
                "status_name": incident["status_name"],
                "phone":       incident["status_phone"],
            },
            "victim": {
                "victim_id":    incident["victim_id"],
                "name":         incident["victim_name"],
                "cnic":         incident["victim_cnic"],
                "email":        incident["victim_email"],
                "phone":        incident["victim_phone"],
                "address":      incident["victim_address"],
                "injury_type":  incident["injury_type"],
            },
            "suspects":        suspects if suspects else [],
            "police_stations": stations if stations else [],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch incident: {str(e)}")
    finally:
        cursor.close()
        conn.close()