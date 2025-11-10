"""
CSV importer for Connections Helper.

Handles reading LinkedIn downloaded connection CSVs, skipping malformed their weird headers,
and returning duplicate lists for the GUI dialog.
"""

import csv
from database import Database, OTHER_NAME, DB_FILE, APP_DIR


def import_csv(path, db: Database):
    """Read a LinkedIn connections CSV and insert new entries."""
    REQUIRED_COLUMNS = {"First Name", "Last Name", "URL", "Email Address", "Company", "Position", "Connected On"}
    duplicates = []

    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    # Find header row
    header_i = 0
    for i, r in enumerate(rows):
        if set([c.strip() for c in r]) >= REQUIRED_COLUMNS:
            header_i = i
            break

    hdr = rows[header_i]
    data = [dict(zip(hdr, r)) for r in rows[header_i + 1:] if any(r)]

    for r in data:
        f = (r.get("First Name") or "").strip()
        l = (r.get("Last Name") or "").strip()
        if not f and not l:
            continue
        u = (r.get("URL") or "").strip()
        e = (r.get("Email Address") or "").strip()
        comp = (r.get("Company") or "").strip()
        pos = (r.get("Position") or "").strip()

        cid = db.get_or_create_company(comp)
        if db.person_exists(f, l, cid, u):
            duplicates.append(f"{f} {l}".strip() or "(no name)")
            continue

        pid = db.add_person(f, l, u, e, cid, pos)
        parts = [pos]
        for sep in ["/", ";", "|", "&", ","]:
            if sep in pos:
                parts = [p.strip() for p in pos.replace("&", ",").replace("|", ",").split(",")]
                break
        db.link_positions(pid, parts)

    return duplicates