import json
import os

import openai
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError


MODEL = "openrouter/free"
MAX_ATTEMPTS = 3


class _StrictModel(BaseModel):
    # Forbids extra fields, so the generated JSON Schema sets
    # "additionalProperties": false — required for OpenAI/OpenRouter strict
    # structured-output mode.
    model_config = ConfigDict(extra="forbid")


class EducationEntry(_StrictModel):
    institution: str
    degree: str
    cgpa: str


class ProjectEntry(_StrictModel):
    project: str
    description: str
    skills: list[str]


class ExperienceEntry(_StrictModel):
    company: str
    position: str
    start_date: str
    end_date: str
    skills: list[str]
    project_titles: list[str]


class ResumeFields(_StrictModel):
    name: str
    skills: list[str]
    education: list[EducationEntry]
    experience: list[ExperienceEntry]
    projects: list[ProjectEntry]


_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "resume_fields",
        "strict": True,
        "schema": ResumeFields.model_json_schema(),
    },
}


load_dotenv()

api_key = os.environ.get("OPENROUTER_API_KEY")

if not api_key:
    raise ValueError("OPENROUTER_API_KEY is not configured.")


_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key,
)


_PROMPT = """
You are a resume information extraction system.

Extract only information explicitly stated in the resume.
Do not guess or infer missing information.

Rules:

1. name
- Return the candidate's full name exactly as written.
- Do not use names of referees, managers, lecturers, companies, or section headings.
- If unclear, return "Not found".

2. skills
- Return all explicitly stated technical and professional skills anywhere in the resume.
- Include skills from Skills, Experience, and Projects sections.
- Do not infer skills from job titles, degrees, or vague responsibilities.
- Do not include company names or qualifications.
- Remove duplicates.
- Skills may also appear inside experience.skills or projects.skills.

3. education
- Create one entry per qualification.
- Match the correct institution to the qualification.
- Extract CGPA/GPA only if stated.
- Use "N/A" if CGPA/GPA is absent.
- Use "Unknown Institution" if no institution is stated.

4. experience
- Extract each paid job, internship, industrial training, or work placement.
- company: employer name, or "Unknown Company".
- position: job title, or "Unknown Position".
- start_date and end_date: preserve the resume's wording.
- Use "Present" only if the resume explicitly indicates the role is ongoing.
- Use "Unknown" if a date cannot be determined.
- skills: skills explicitly associated with that job.
- project_titles: titles of projects from the projects list that were completed during that job.
- Do not include volunteering or education.

5. projects
- Extract every clearly identifiable project, including academic, personal, side, and work-related projects.
- project: project title, or "Untitled Project" if no title is stated.
- description: one short sentence describing the project's purpose. Do not invent details.
- skills: tools, languages, or frameworks explicitly associated with that project.
- Do not include education or general work duties as projects.

Return JSON matching the required schema.

Resume:
--------------------
{text}
--------------------
"""


def _extract_once(text: str) -> ResumeFields:

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "user",
                "content": _PROMPT.replace("{text}", text),
            }
        ],
        response_format=_RESPONSE_FORMAT,
    )

    if not response.choices:
        raise ValueError("OpenRouter returned no choices in the response.")

    result_text = response.choices[0].message.content

    if not result_text:
        raise ValueError("OpenRouter returned an empty response.")

    # Free models routed via "openrouter/free" sometimes wrap JSON in markdown
    # fences despite response_format — strip those before parsing.
    result_text = result_text.strip()
    if result_text.startswith("```"):
        result_text = result_text.strip("`")
        if result_text.startswith("json"):
            result_text = result_text[4:]
        result_text = result_text.strip()

    # Convert the JSON text from the LLM into a Python dictionary
    data = json.loads(result_text)

    # Validate it using your existing Pydantic model
    return ResumeFields.model_validate(data)


def extract_llm_fields(text: str) -> ResumeFields:
    # "openrouter/free" routes to a different, randomly-picked free model each
    # call, so a failure (empty choices, malformed JSON, etc.) on one attempt
    # often just means that particular model had a bad moment — retry a few
    # times before giving up, since the next attempt likely lands on a
    # different, working model.
    last_error = None
    for _ in range(MAX_ATTEMPTS):
        try:
            return _extract_once(text)
        except (ValueError, json.JSONDecodeError, ValidationError, openai.APIError) as e:
            last_error = e
    raise RuntimeError(
        f"OpenRouter failed after {MAX_ATTEMPTS} attempts. Last error: {last_error}"
    ) from last_error