"""
Database module for Connections Helper.

Handles all persistence logic: companies, people, positions, and settings.
Uses SQLite for storage, auto-creates tables if missing.
"""

import sqlite3
import os

APP_DIR = os.path.expanduser("~/Library/Application Support/ConnectionsHelper")
os.makedirs(APP_DIR, exist_ok=True)
DB_FILE = os.path.join(APP_DIR, "connections.db")

OTHER_NAME = "Other_Unknown"

class Database:
    """Encapsulates all database operations for the application."""

    def __init__(self, path: str = DB_FILE):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

        # Set default employee threshold
        if self.get_setting("employee_threshold") is None:
            self.set_setting("employee_threshold", "10")
        

    def create_tables(self):
        """Create all tables if they do not already exist."""
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS companies(
            id INTEGER PRIMARY KEY,
            name_original TEXT,
            name_norm TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS positions(
            id INTEGER PRIMARY KEY,
            name_original TEXT,
            name_norm TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS people(
            id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            url TEXT,
            email TEXT,
            company_id INTEGER,
            position_raw TEXT,
            visited INTEGER DEFAULT 0,
            FOREIGN KEY(company_id) REFERENCES companies(id)
        );
        CREATE TABLE IF NOT EXISTS person_positions(
            person_id INTEGER,
            position_id INTEGER,
            PRIMARY KEY(person_id, position_id)
        );
        CREATE TABLE IF NOT EXISTS settings(
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        self.conn.commit()

    # Settings
    def get_setting(self, key: str):
        """Retrieve a setting value by key."""
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str):
        """Insert or update a setting value."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO settings(key, value)
            VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value;
        """, (key, value))
        self.conn.commit()

    # Company and position helpers
    @staticmethod
    def norm_company(name):
        """Normalize company names for grouping."""
        if not name:
            return OTHER_NAME
        n = name.strip().lower()
        if any(k in n for k in ["self", "freelance", "independent", "unknown", "n/a"]):
            return OTHER_NAME
        return " ".join(n.split())

    @staticmethod
    def norm_position(p):
        """Normalize position names."""
        return " ".join((p or "").strip().lower().split())

    def get_or_create_company(self, name):
        """Return an existing or new company ID."""
        norm = self.norm_company(name)
        c = self.conn.cursor()
        c.execute("SELECT id FROM companies WHERE name_norm=?", (norm,))
        row = c.fetchone()
        if row:
            return row["id"]
        c.execute("INSERT INTO companies(name_original, name_norm) VALUES(?, ?)", (name or OTHER_NAME, norm))
        self.conn.commit()
        return c.lastrowid

    def get_or_create_position(self, pos):
        """Return an existing or new position ID."""
        norm = self.norm_position(pos)
        c = self.conn.cursor()
        c.execute("SELECT id FROM positions WHERE name_norm=?", (norm,))
        row = c.fetchone()
        if row:
            return row["id"]
        c.execute("INSERT INTO positions(name_original, name_norm) VALUES(?, ?)", (pos, norm))
        self.conn.commit()
        return c.lastrowid


    # People
    def person_exists(self, f, l, cid, url):
        """Check whether a person already exists in the DB."""
        cur = self.conn.cursor()
        if url:
            cur.execute("SELECT id FROM people WHERE url=?", (url,))
            if cur.fetchone():
                return True
        cur.execute("SELECT id FROM people WHERE first_name=? AND last_name=? AND company_id=?", (f, l, cid))
        return bool(cur.fetchone())

    def add_person(self, f, l, u, e, cid, pos):
        """Insert a new person record."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO people(first_name, last_name, url, email, company_id, position_raw)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (f, l, u, e, cid, pos))
        self.conn.commit()
        return cur.lastrowid

    def link_positions(self, pid, poslist):
        """Link person to multiple positions."""
        cur = self.conn.cursor()
        for p in poslist:
            if not p.strip():
                continue
            pid2 = self.get_or_create_position(p)
            cur.execute("INSERT OR IGNORE INTO person_positions(person_id, position_id) VALUES(?, ?)", (pid, pid2))
        self.conn.commit()

    def mark_visited(self, ids):
        """Mark a list of people as visited."""
        self.conn.executemany("UPDATE people SET visited=1 WHERE id=?", [(i,) for i in ids])
        self.conn.commit()


    def unmark_visited(self, ids):
        """Undo visited flag for a list of people."""
        self.conn.executemany("UPDATE people SET visited=0 WHERE id=?", [(i,) for i in ids])
        self.conn.commit()


    def delete_people(self, ids):
        """Delete people and their position links."""
        c = self.conn.cursor()
        c.executemany("DELETE FROM person_positions WHERE person_id=?", [(i,) for i in ids])
        c.executemany("DELETE FROM people WHERE id=?", [(i,) for i in ids])
        self.conn.commit()


    # Queries
    def get_all_people(self):
        """Return all people, joined with their company names."""
        q = """
        SELECT p.*, c.name_original AS company
        FROM people p
        LEFT JOIN companies c ON p.company_id = c.id
        ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
        """
        return self.conn.execute(q).fetchall()


    def get_unvisited_people(self, companies=None):
        """Return only people who have not been visited."""
        cur = self.conn.cursor()
        if companies:
            qs = ",".join("?" * len(companies))
            q = f"""
            SELECT p.*, c.name_original AS company
            FROM people p
            JOIN companies c ON p.company_id = c.id
            WHERE p.visited=0 AND c.id IN ({qs})
            ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
            """
            return cur.execute(q, companies).fetchall()

        q = """
        SELECT p.*, c.name_original AS company
        FROM people p
        LEFT JOIN companies c ON p.company_id=c.id
        WHERE p.visited=0
        ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
        """
        return cur.execute(q).fetchall()

    def get_people_filtered(self, companies=None):
        """Return people filtered by a list of company IDs."""
        cur = self.conn.cursor()
        if companies:
            qs = ",".join("?" * len(companies))
            q = f"""
            SELECT p.*, c.name_original AS company
            FROM people p
            JOIN companies c ON p.company_id = c.id
            WHERE c.id IN ({qs})
            ORDER BY p.last_name COLLATE NOCASE, p.first_name COLLATE NOCASE
            """
            return cur.execute(q, companies).fetchall()
        return self.get_all_people()

    def companies(self):
        """Return all companies with >= threshold employees (from settings)."""
        threshold = int(self.get_setting("employee_threshold") or 3)
        q = """
        SELECT c.id, c.name_original, COUNT(p.id) AS num
        FROM companies c
        JOIN people p ON p.company_id = c.id
        GROUP BY c.id
        HAVING COUNT(p.id) >= ?
        ORDER BY c.name_original COLLATE NOCASE
        """
        return self.conn.execute(q, (threshold,)).fetchall()

    def visited_stats(self):
        """Return (visited_count, total_count)."""
        v = self.conn.execute("SELECT COUNT(*) FROM people WHERE visited=1").fetchone()[0]
        t = self.conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
        return v, t