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
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def save_resume(filename: str, data: dict):
    conn = sqlite3.connect(DB_NAME)
    conn.execute(
        """
        INSERT INTO resumes (filename, name, email, phone, skills, education)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            data["name"],
            data["email"],
            data["phone"],
            ", ".join(data["skills"]),
            " | ".join(data["education"]),
        ),
    )
    conn.commit()
    conn.close()


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
