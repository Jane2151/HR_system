import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

MODEL = "gemini-3.6-flash"


class EducationEntry(BaseModel):
    institution: str
    degree: str
    cgpa: str


class ResumeFields(BaseModel):
    name: str
    skills: list[str]
    education: list[EducationEntry]

load_dotenv()

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

_PROMPT = """You are extracting structured fields from a resume's raw text.

Rules:
- name: the candidate's full name as it appears on the resume. Use "Not found" if it can't be determined.
- skills: technical and professional skills explicitly mentioned (tools, languages, frameworks, soft skills). Only include skills actually present in the text, do not invent any.
- education: one entry per degree/qualification found. For each, give the institution and CGPA/GPA if stated. Use "N/A" for cgpa if not stated, and "Unknown Institution" if the institution isn't stated.

Resume text:
---
{text}
---"""


def extract_llm_fields(text: str) -> ResumeFields:
    response = _client.models.generate_content(
        model=MODEL,
        contents=_PROMPT.format(text=text),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ResumeFields,
        ),
    )
    return response.parsed
