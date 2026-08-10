import sqlite3
import pandas as pd

DB_NAME = "resumes.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            filename    TEXT,
            name        TEXT,
            email       TEXT,
            phone       TEXT,
            skills      TEXT,
            education   TEXT,
            experience  TEXT,
            projects    TEXT,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing databases created before these columns existed.
    # SQLite has no "ADD COLUMN IF NOT EXISTS", so check first.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(resumes)")}
    for column in ("experience", "projects"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE resumes ADD COLUMN {column} TEXT")
    conn.commit()
    conn.close()


def _serialize_entries(entries: list[dict]) -> str:
    """Flatten {'header', 'bullets'} entries into plain text for TEXT column storage."""
    blocks = []
    for entry in entries:
        block = entry["header"]
        if entry["bullets"]:
            block += " | " + "; ".join(entry["bullets"])
        blocks.append(block)
    return " || ".join(blocks)


def save_resume(filename: str, data: dict):
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        """
        INSERT INTO resumes (filename, name, email, phone, skills, education, experience, projects)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            data["name"],
            data["email"],
            data["phone"],
            ", ".join(data["skills"]),
            " | ".join(data["education"]),
            _serialize_entries(data["experience"]),
            _serialize_entries(data["projects"]),
        ),
    )
    conn.commit()
    conn.close()


def find_duplicate(email: str):
    """Return (name, uploaded_at) of an existing resume with this email, or None."""
    if not email or email == "Not found":
        return None
    conn = sqlite3.connect(DB_NAME)
    row = conn.execute(
        "SELECT name, uploaded_at FROM resumes WHERE email = ? LIMIT 1", (email,)
    ).fetchone()
    conn.close()
    return row


def get_all_resumes() -> pd.DataFrame:
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        "SELECT * FROM resumes ORDER BY uploaded_at DESC", conn
    )
    conn.close()
    return df


def delete_resume(record_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.execute("DELETE FROM resumes WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()
