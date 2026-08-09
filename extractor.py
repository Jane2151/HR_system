import re

import pdfplumber

from llm_extractor import extract_llm_fields


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


def parse_resume(pdf_path: str) -> dict:
    text = extract_text(pdf_path)
    llm_fields = extract_llm_fields(text)
    return {
        "name": llm_fields.name,
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": llm_fields.skills,
        "education": _format_education(llm_fields.education),
    }
