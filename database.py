import sqlite3
import pandas as pd

DB_NAME = "resumes.db"

# Hiring pipeline stages, in order. A new save always starts at the first stage.
PIPELINE_STAGES = ["Screening", "Shortlisted", "Interview", "Offer"]


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
            status      TEXT DEFAULT 'Screening',
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Migrate existing databases created before these columns existed.
    # SQLite has no "ADD COLUMN IF NOT EXISTS", so check first.
    existing_columns = {row[1] for row in conn.execute("PRAGMA table_info(resumes)")}
    for column in ("experience", "projects"):
        if column not in existing_columns:
            conn.execute(f"ALTER TABLE resumes ADD COLUMN {column} TEXT")
    if "status" not in existing_columns:
        conn.execute("ALTER TABLE resumes ADD COLUMN status TEXT DEFAULT 'Screening'")
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
        INSERT INTO resumes (filename, name, email, phone, skills, education, experience, projects, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            PIPELINE_STAGES[0],
        ),
    )
    conn.commit()
    conn.close()


def update_status(record_id: int, status: str) -> None:
    conn = sqlite3.connect(DB_NAME)
    conn.execute("UPDATE resumes SET status = ? WHERE id = ?", (status, record_id))
    conn.commit()
    conn.close()


def get_pipeline_counts() -> dict:
    """Candidate count per pipeline stage, in PIPELINE_STAGES order (0 if none)."""
    conn = sqlite3.connect(DB_NAME)
    rows = conn.execute("SELECT status, COUNT(*) FROM resumes GROUP BY status").fetchall()
    conn.close()
    counts = dict(rows)
    return {stage: counts.get(stage, 0) for stage in PIPELINE_STAGES}


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
