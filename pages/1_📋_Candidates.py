import html
import re

import pandas as pd
import streamlit as st

from database import PIPELINE_STAGES, delete_resume, get_all_resumes, update_status

st.set_page_config(page_title="Candidate", page_icon="📋", layout="wide")


def _safe_text(value) -> str:
    return "" if pd.isna(value) else str(value)


def _render_box(inner_html: str) -> None:
    # Fixed light background with an explicit dark text color, so the box stays
    # readable regardless of the viewer's light/dark Streamlit theme.
    st.markdown(
        f'<div style="background:#f0f2f6;color:#1a1a1a;border-left:4px solid #0078D4;'
        f'padding:8px 12px;margin-bottom:8px;border-radius:4px;font-size:14px">'
        f'{inner_html}</div>',
        unsafe_allow_html=True,
    )


def _render_entries(entries: list[dict]) -> None:
    for entry in entries:
        inner = f"<strong>{html.escape(entry['header'])}</strong>"
        if entry["bullets"]:
            bullets_html = "".join(f"<li>{html.escape(b)}</li>" for b in entry["bullets"])
            inner += f'<ul style="margin:6px 0 0 0;padding-left:18px">{bullets_html}</ul>'
        _render_box(inner)


def _parse_entries(serialized: str) -> list[dict]:
    """Inverse of database._serialize_entries — split the flattened text
    stored in the experience/projects columns back into display entries."""
    serialized = serialized.strip()
    if not serialized:
        return []
    entries = []
    for block in serialized.split(" || "):
        if " | " in block:
            header, bullets_str = block.split(" | ", 1)
            bullets = bullets_str.split("; ")
        else:
            header, bullets = block, []
        entries.append({"header": header, "bullets": bullets})
    return entries


_EDUCATION_LEVEL_KEYWORDS = [
    (4, ("phd", "ph.d", "doctorate", "doctor of philosophy", "doktor")),
    (3, ("master", "m.sc", "msc", "m.eng", "meng", "mba")),
    (2, ("bachelor", "degree", "b.sc", "bsc", "b.eng", "beng", "undergraduate", "sarjana muda")),
    (1, ("foundation", "diploma", "certificate", "sijil", "pre-u", "pre-university", "stpm", "matriculation", "a-level")),
]


def _education_level(degree_text: str) -> int:
    """Rough ranking of a qualification's level, used to pick the candidate's
    highest one when several are listed (e.g. Foundation + Degree)."""
    text = degree_text.lower()
    if "sarjana muda" in text:
        return 2  # Malay for "Bachelor" — check before the bare "sarjana" (Master) match below
    for level, keywords in _EDUCATION_LEVEL_KEYWORDS:
        if any(kw in text for kw in keywords):
            return level
    if "sarjana" in text:
        return 3  # Malay for "Master"
    return 0


def _parse_education_summary(education_text: str) -> tuple[str, str]:
    """Pick the candidate's highest-level qualification (e.g. Degree over
    Foundation) out of the stored 'Institution — Degree (CGPA: X)' | ... string,
    and return that entry's (university, cgpa) — not a mix of every entry."""
    best = None  # (level, university, cgpa)
    for entry in education_text.split(" | "):
        match = re.match(r"^(.*?)\s—\s(.*?)\s\(CGPA:\s*(.*?)\)$", entry.strip())
        if not match:
            continue
        institution, degree, cgpa = (g.strip() for g in match.groups())
        level = _education_level(degree)
        if best is None or level > best[0]:
            best = (level, institution, cgpa)

    if best is None:
        return "Not listed", "N/A"
    _, university, cgpa = best
    return university, cgpa if cgpa and cgpa.upper() != "N/A" else "N/A"


def _cgpa_sort_value(cgpa_text: str) -> float:
    """First numeric CGPA found, for sorting. Candidates with no CGPA sort last (ascending)."""
    match = re.search(r"[0-4]\.\d+", cgpa_text)
    return float(match.group()) if match else -1.0


def _all_skills(skills_text: str, experience_text: str, projects_text: str) -> list[str]:
    """Combine the dedicated skills column with any 'Skills: ...' mentions
    embedded inside the stored experience/projects text."""
    skills = {s.strip() for s in skills_text.split(",") if s.strip()}
    for text in (experience_text, projects_text):
        for match in re.finditer(r"Skills:\s*([^;|)]+)", text):
            skills.update(s.strip() for s in match.group(1).split(",") if s.strip())
    return sorted(skills, key=str.lower)


def _chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _sort_label(field: str, label: str) -> str:
    if st.session_state["sort_field"] == field:
        return f"{label} {'▲' if st.session_state['sort_ascending'] else '▼'}"
    return label


def _toggle_sort(field: str) -> None:
    if st.session_state["sort_field"] == field:
        st.session_state["sort_ascending"] = not st.session_state["sort_ascending"]
    else:
        st.session_state["sort_field"] = field
        st.session_state["sort_ascending"] = True


@st.dialog("Candidate Profile", width="large")
def _show_candidate_dialog(record: dict) -> None:
    st.subheader(f"👤 {record['name']}")
    st.write(f"**Email:** {record['email']}")
    st.write(f"**Phone:** {record['phone']}")
    st.write(f"**Pipeline Stage:** {record['status']}")

    action_col1, action_col2 = st.columns(2)
    with action_col1:
        if record["status"] == PIPELINE_STAGES[0]:
            if st.button("⭐ Move to Shortlisted"):
                update_status(record["id"], "Shortlisted")
                st.rerun()
    with action_col2:
        if st.button("🗑️ Delete Candidate"):
            delete_resume(record["id"])
            st.rerun()

    st.markdown("**🎓 Education**")
    education_entries = [e.strip() for e in record["education_text"].split(" | ") if e.strip()]
    if education_entries:
        for entry in education_entries:
            _render_box(html.escape(entry))
    else:
        st.info("No education listed.")

    st.markdown("**🛠️ Other Skills**")
    other_skills = [s.strip() for s in record["skills_text"].split(",") if s.strip()]
    if other_skills:
        badge_html = " ".join(
            f'<span style="background:#0078D4;color:white;padding:4px 10px;'
            f'border-radius:12px;margin:3px;display:inline-block;font-size:13px">'
            f'{html.escape(skill)}</span>'
            for skill in other_skills
        )
        st.markdown(badge_html, unsafe_allow_html=True)
    else:
        st.info("No other skills listed.")

    st.markdown("**💼 Experience**")
    experience_entries = _parse_entries(record["experience_text"])
    if experience_entries:
        _render_entries(experience_entries)
    else:
        st.info("No work experience listed.")

    st.markdown("**🧩 Independent Projects**")
    project_entries = _parse_entries(record["projects_text"])
    if project_entries:
        _render_entries(project_entries)
    else:
        st.info("No independent projects listed.")


st.title("📋 Candidate")
st.markdown("Click a **skill** to filter, click a **column header** to sort.")
st.divider()

df = get_all_resumes()

if df.empty:
    st.info("No resumes saved yet. Go to the main page to upload and save one.")
else:
    st.session_state.setdefault("skill_filter", set())
    st.session_state.setdefault("sort_field", "name")
    st.session_state.setdefault("sort_ascending", True)

    # ── Precompute display fields for every saved candidate ──────────────────
    records = []
    for _, row in df.iterrows():
        education_text = _safe_text(row["education"])
        skills_text = _safe_text(row["skills"])
        experience_text = _safe_text(row["experience"])
        projects_text = _safe_text(row["projects"])
        university, cgpa = _parse_education_summary(education_text)
        records.append({
            "id": int(row["id"]),
            "name": _safe_text(row["name"]),
            "email": _safe_text(row["email"]),
            "phone": _safe_text(row["phone"]),
            "skills_text": skills_text,
            "education_text": education_text,
            "experience_text": experience_text,
            "projects_text": projects_text,
            "university": university,
            "cgpa": cgpa,
            "cgpa_sort": _cgpa_sort_value(cgpa),
            "all_skills": _all_skills(skills_text, experience_text, projects_text),
            "status": _safe_text(row["status"]) or PIPELINE_STAGES[0],
        })

    # ── Skill filter (clicking a skill badge below toggles this) ─────────────
    if st.session_state["skill_filter"]:
        active = ", ".join(sorted(st.session_state["skill_filter"], key=str.lower))
        col_a, col_b = st.columns([5, 1])
        col_a.markdown(f"**Filtering by:** {active}  _(showing candidates with any of these)_")
        if col_b.button("✖ Clear filters", width="stretch"):
            st.session_state["skill_filter"] = set()
            st.rerun()
        records = [r for r in records if st.session_state["skill_filter"] & set(r["all_skills"])]
        st.divider()

    # ── Apply sort (name ascending is the fixed baseline; CGPA is user-togglable) ─
    sort_key = {
        "name": lambda r: r["name"].lower(),
        "cgpa": lambda r: r["cgpa_sort"],
    }[st.session_state["sort_field"]]
    records.sort(key=sort_key, reverse=not st.session_state["sort_ascending"])

    st.metric("Candidates Shown", len(records))
    st.divider()

    # ── Header row (only CGPA is sortable) ────────────────────────────────────
    header = st.columns([2, 3, 2, 1, 1])
    header[0].markdown("**Name**")
    header[1].markdown("**All Skills**")
    header[2].markdown("**University**")
    if header[3].button(_sort_label("cgpa", "CGPA"), key="sort_cgpa", width="stretch"):
        _toggle_sort("cgpa")
        st.rerun()
    header[4].markdown("**Action**")
    st.divider()

    for record in records:
        cols = st.columns([2, 3, 2, 1, 1])
        cols[0].write(record["name"])

        with cols[1]:
            if record["all_skills"]:
                for skill_chunk in _chunk(record["all_skills"], 3):
                    skill_cols = st.columns(len(skill_chunk))
                    for skill_col, skill in zip(skill_cols, skill_chunk):
                        selected = skill in st.session_state["skill_filter"]
                        label = f"✓ {skill}" if selected else skill
                        if skill_col.button(label, key=f"skill_{record['id']}_{skill}", width="stretch"):
                            if selected:
                                st.session_state["skill_filter"].discard(skill)
                            else:
                                st.session_state["skill_filter"].add(skill)
                            st.rerun()
            else:
                st.write("None listed")

        cols[2].write(record["university"])
        cols[3].write(record["cgpa"])

        if cols[4].button("🔍 View", key=f"view_{record['id']}"):
            _show_candidate_dialog(record)

        st.divider()
