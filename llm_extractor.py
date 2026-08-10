import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError


MODEL = "openrouter/free"
MAX_ATTEMPTS = 3


class EducationEntry(BaseModel):
    institution: str
    degree: str
    cgpa: str


class ProjectEntry(BaseModel):
    project: str
    description: str
    skills: list[str]


class ExperienceEntry(BaseModel):
    company: str
    position: str
    start_date: str
    end_date: str
    skills: list[str]
    projects: list[ProjectEntry]


class ResumeFields(BaseModel):
    name: str
    other_skills: list[str]
    education: list[EducationEntry]
    experience: list[ExperienceEntry]
    projects: list[ProjectEntry]


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

Extract structured information ONLY from the supplied resume.

STRICT RULES:

1. Do not guess or invent information.

2. name:
   - Return the candidate's full name exactly as stated.
   - Do not return a referee, lecturer, manager, company name,
     job title, or section heading.
   - If the candidate name cannot be determined, return "Not found".

3. other_skills:
   - Skills belong to whichever section they are demonstrated in. A skill
     mentioned inside a Work Experience entry (or a project nested under it)
     belongs in that entry's own "skills" list (rule 5). A skill mentioned
     inside an independent Projects entry belongs in that project's own
     "skills" list (rule 6).
   - other_skills is ONLY for skills that are NOT already captured in any
     experience or project entry — typically a standalone "Skills" section,
     or soft skills mentioned outside any specific job/project.
   - A skill only counts if it is explicitly named as something used or applied.
     Do not infer skills merely from a job title, degree, or vague responsibility
     (e.g. do not infer "Leadership" just because someone was a "Team Lead"
     unless leadership/management is explicitly mentioned).
   - Do not include company names or education qualifications.
   - Remove duplicate skills, and never repeat a skill that already appears
     under an experience or project entry.

4. education:
   - Create one entry for each qualification.
   - Match each qualification with its correct institution.
   - Extract CGPA/GPA only if explicitly stated.
   - If CGPA/GPA is absent, return "N/A".
   - If the institution cannot be found, return "Unknown Institution".

5. experience:
   - Extract each clearly identifiable paid job, internship, industrial training, or work placement, regardless of the exact section heading.
   - company: the employer name. If it cannot be found, return "Unknown Company".
   - position: the job title held. If it cannot be found, return "Unknown Position".
   - start_date: exactly as written on the resume (e.g. "Jan 2020", "2020", "March 2021").
   - end_date: exactly as written on the resume. If the role is ongoing, return
     "Present". If it cannot be determined, return "Unknown".
   - Do not calculate durations yourself — only return the raw dates as written.
   - skills: tools, languages, or frameworks explicitly named in that job's own
     description, outside of any specific named project (e.g. "used Jira and
     Confluence daily" -> Jira, Confluence for that entry). Empty list if none.
   - projects: any specific, named initiative described under this job
     (e.g. "Led development of the Customer Portal using React and Node.js"
     while working at Company X). Use the same fields as rule 6 (project,
     description, skills), scoped to just that initiative. Empty list if the
     job description has no distinct named projects, just general duties.
   - Do not include unpaid volunteering or education here.

6. projects (independent):
   - Create one entry ONLY for projects that stand on their own — under a
     Projects / Personal Projects / Academic Projects / Side Projects section,
     NOT tied to a specific employer listed in rule 5. If a project is
     explicitly described as done while working at a company, put it under
     that experience entry's own "projects" list instead (rule 5), not here.
   - project: the project's name/title. If it cannot be found, return "Untitled Project".
   - description: ONE short sentence (roughly 15-20 words max) stating what
     the project actually does/did — its purpose or function, in plain terms
     (e.g. "A mobile app that lets students book campus facilities online").
     Do not fill this with tool/language/framework names — those already go
     in the separate "skills" field below, so avoid repeating them here.
     Do not invent details that aren't stated, and do not copy multiple
     resume bullet points verbatim — condense them. If no description is
     given, return "".
   - skills: tools, languages, or frameworks explicitly named in that project's
     description. Empty list if none are named.
   - Do not include work experience or education here.

Return JSON ONLY using exactly this structure:

{
    "name": "string",
    "other_skills": ["string"],
    "education": [
        {
            "institution": "string",
            "degree": "string",
            "cgpa": "string"
        }
    ],
    "experience": [
        {
            "company": "string",
            "position": "string",
            "start_date": "string",
            "end_date": "string",
            "skills": ["string"],
            "projects": [
                {
                    "project": "string",
                    "description": "string",
                    "skills": ["string"]
                }
            ]
        }
    ],
    "projects": [
        {
            "project": "string",
            "description": "string",
            "skills": ["string"]
        }
    ]
}

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
        response_format={"type": "json_object"},
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
        except (ValueError, json.JSONDecodeError, ValidationError) as e:
            last_error = e
    raise RuntimeError(
        f"OpenRouter failed after {MAX_ATTEMPTS} attempts. Last error: {last_error}"
    ) from last_error