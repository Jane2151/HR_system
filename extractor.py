import re
from datetime import datetime

import pdfplumber
from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

from llm_extractor import extract_llm_fields

_ONGOING_MARKERS = {"present", "current", "currently", "now", "ongoing", "n/a", "unknown", ""}


def extract_text(pdf_path: str) -> str:
    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def extract_email(text: str) -> str:
    matches = re.findall(r"[\w\.\+\-]+@[\w\.\-]+\.\w{2,}", text)
    return matches[0] if matches else "Not found"


def extract_phone(text: str) -> str:
    matches = re.findall(r"[\+]?[\d][\d\s\-\.\(\)]{7,}[\d]", text)
    # filter out short noise like years
    matches = [m.strip() for m in matches if len(re.sub(r"\D", "", m)) >= 8]
    return matches[0] if matches else "Not found"


def _format_education(entries) -> list[str]:
    if not entries:
        return ["Education not clearly listed"]
    return [
        f"{entry.institution} — {entry.degree} (CGPA: {entry.cgpa})"
        for entry in entries
    ]


def _parse_date(value: str):
    if not value or value.strip().lower() in _ONGOING_MARKERS:
        return None
    try:
        return date_parser.parse(value, default=datetime(datetime.now().year, 1, 1), fuzzy=True)
    except (ValueError, OverflowError):
        return None


def _format_duration(start_date: str, end_date: str) -> str:
    start = _parse_date(start_date)
    if start is None:
        return "Unknown duration"

    end = _parse_date(end_date) or datetime.today()
    if end < start:
        return "Unknown duration"

    delta = relativedelta(end, start)
    parts = []
    if delta.years:
        parts.append(f"{delta.years} yr{'s' if delta.years != 1 else ''}")
    if delta.months:
        parts.append(f"{delta.months} mo{'s' if delta.months != 1 else ''}")
    return " ".join(parts) if parts else "Less than a month"


def _truncate(text: str, limit: int = 160) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _format_project_bullet(entry) -> str:
    text = f"Project: {entry.project}"
    if entry.description:
        text += f" — {_truncate(entry.description)}"
    if entry.skills:
        text += f" (Skills: {', '.join(entry.skills)})"
    return text


def _match_experience_projects(experience_entries, project_entries):
    """Join each experience entry to its projects by title (case-insensitive).

    Returns (experience_projects, independent_projects):
    - experience_projects: list parallel to experience_entries, each the list
      of matched ProjectEntry objects for that job.
    - independent_projects: projects not referenced by any experience entry.
    """
    projects_by_title = {p.project.strip().lower(): p for p in project_entries}
    linked_titles = set()

    experience_projects = []
    for entry in experience_entries:
        matched = []
        for title in entry.project_titles:
            key = title.strip().lower()
            project = projects_by_title.get(key)
            if project:
                matched.append(project)
                linked_titles.add(key)
        experience_projects.append(matched)

    independent_projects = [
        p for p in project_entries if p.project.strip().lower() not in linked_titles
    ]
    return experience_projects, independent_projects


def _compute_other_skills(all_skills: list[str], experience_entries, project_entries) -> list[str]:
    """Skills not already covered by any experience or project's own skills list."""
    used = {s.strip().lower() for p in project_entries for s in p.skills}
    used |= {s.strip().lower() for e in experience_entries for s in e.skills}
    return [s for s in all_skills if s.strip().lower() not in used]


def _format_experience(experience_entries, experience_projects) -> list[dict]:
    """Return one {'header': str, 'bullets': list[str]} per job, for bullet-point display."""
    results = []
    for entry, matched_projects in zip(experience_entries, experience_projects):
        end_label = "Present" if entry.end_date.strip().lower() in _ONGOING_MARKERS else entry.end_date
        duration = _format_duration(entry.start_date, entry.end_date)
        bullets = []
        if entry.skills:
            bullets.append("Skills: " + ", ".join(entry.skills))
        bullets.extend(_format_project_bullet(p) for p in matched_projects)
        results.append({
            "header": f"{entry.position} at {entry.company} "
                      f"({entry.start_date} – {end_label}, {duration})",
            "bullets": bullets,
        })
    return results


def _format_projects(entries) -> list[dict]:
    """Return one {'header': str, 'bullets': list[str]} per independent project."""
    results = []
    for entry in entries:
        bullets = []
        if entry.description:
            bullets.append(_truncate(entry.description))
        if entry.skills:
            bullets.append(f"Skills: {', '.join(entry.skills)}")
        results.append({
            "header": entry.project,
            "bullets": bullets,
        })
    return results


def parse_resume(pdf_path: str) -> dict:
    text = extract_text(pdf_path)
    llm_fields = extract_llm_fields(text)

    experience_projects, independent_projects = _match_experience_projects(
        llm_fields.experience, llm_fields.projects
    )

    return {
        "name": llm_fields.name,
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": _compute_other_skills(llm_fields.skills, llm_fields.experience, llm_fields.projects),
        "education": _format_education(llm_fields.education),
        "experience": _format_experience(llm_fields.experience, experience_projects),
        "projects": _format_projects(independent_projects),
    }
