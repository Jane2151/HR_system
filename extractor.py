import pdfplumber
import spacy
import re

nlp = spacy.load("en_core_web_sm")

SKILLS_LIST = [
    "Python", "Power BI", "Excel", "SQL", "Tableau", "Machine Learning",
    "Deep Learning", "Data Analysis", "Data Visualization", "JavaScript",
    "Java", "C++", "R", "TensorFlow", "Pandas", "NumPy", "Streamlit",
    "MySQL", "PostgreSQL", "MongoDB", "Git", "Docker", "AWS", "Azure",
    "Figma", "Photoshop", "Communication", "Leadership", "Teamwork",
    "Problem Solving", "Project Management", "Microsoft Office", "SAP",
    "Agile", "Scrum", "NLP", "Computer Vision", "AutoCAD", "Canva",
    "HTML", "HTML5", "CSS", "CSS3", "PHP","Langchain","C","C#",
]

EDUCATION_KEYWORDS = [
    "bachelor", "master", "phd", "diploma", "degree",
    "b.sc", "m.sc", "mba", "university", "college", "institute",
    "b.eng", "m.eng", "foundation", "sijil", "sarjana", "doktor",
    "CGPA",
]


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


def extract_name(text: str) -> str:
    lines = text.split("\n")
    clean_lines = [line.strip() for line in lines if len(line.strip()) > 0]
    
    # 1. Check for Malay and Indian name markers in the top 10 lines
    malaysian_markers = [" bin ", " binti ", " bt ", " a/l ", " a/p "]
    
    for line in clean_lines[:10]:
        line_lower = line.lower()
        for marker in malaysian_markers:
            if marker in line_lower:
                # We use .title() to capitalize names, but fix a/l and a/p so they stay lowercase
                name = line.title()
                name = name.replace(" A/L ", " a/l ").replace(" A/P ", " a/p ")
                return name

    # 2. First Line Trick (Great for Chinese names with 3 to 4 words)
    if clean_lines:
        first_line = clean_lines[0]
        word_count = len(first_line.split())
        
        # Check if the line has between 2 and 6 words
        if 1 < word_count <= 6:
            return first_line.title()

    # 3. Backup Plan: Use the AI model if the rules above fail
    doc = nlp(text[:800])
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            return ent.text.strip().title()
            
    return "Not found"


def extract_skills(text: str) -> list[str]:
    found = []
    for skill in SKILLS_LIST:
        if len(skill) == 1:
            # SUPER STRICT RULE for 1-letter skills like 'R' or 'C'
            # Only match if it is clearly formatted as a skill.
            pattern = (
                r"(?:[,/|]\s*" + re.escape(skill) + r"\b)|"         # Next to punctuation: ", R"
                r"(?:\b" + re.escape(skill) + r"\s*[,/|])|"         # Next to punctuation: "R ,"
                r"(?:\b" + re.escape(skill) + r"\s+programming\b)|" # With keyword: "R programming"
                r"(?:^[^\w]*" + re.escape(skill) + r"\s*$)"         # As a bullet point: "• R"
            )
            # MULTILINE allows the '^' and '$' to check line-by-line for bullet points
            flags = re.MULTILINE  
        else:
            # NORMAL RULE for longer skills like 'Python'
            pattern = r"(?<!\w)" + re.escape(skill) + r"(?!\w)"
            flags = re.IGNORECASE
            
        if re.search(pattern, text, flags):
            found.append(skill)
            
    return found


# ── Section boundary patterns ────────────────────────────────────────────────
_EDU_SECTION_HEADERS = re.compile(
    r"^\s*(education|academic|qualification|academic background|educational background)\s*$",
    re.IGNORECASE,
)
_NEXT_SECTION = re.compile(
    r"^\s*(experience|work experience|employment|skills|technical skills|"
    r"projects?|achievements?|awards?|certifications?|references?|languages?|"
    r"summary|objective|profile|activities|extracurricular|hobbies|interests)\s*$",
    re.IGNORECASE,
)


def _isolate_education_section(text: str) -> str:
    """Return only the raw lines inside the Education section header block.
    Returns empty string if no header is found (caller falls back to full text)."""
    lines = text.split("\n")
    in_edu = False
    edu_lines = []
    for line in lines:
        stripped = line.strip()
        if _EDU_SECTION_HEADERS.match(stripped):
            in_edu = True
            continue
        if in_edu:
            if _NEXT_SECTION.match(stripped):
                break
            edu_lines.append(line)
    return "\n".join(edu_lines)


def extract_education(text: str) -> list[str]:
    # 1. Isolate the education section
    edu_block = _isolate_education_section(text)
    search_text = edu_block if edu_block.strip() else text

    valid_levels = [
        kw for kw in EDUCATION_KEYWORDS
        if kw.lower() not in ["cgpa", "university", "college", "institute"]
    ]

    stop_words = {
        "education", "present", "now", "current",
        "january", "february", "march", "april", "may", "june",
        "july", "august", "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    }

    # 2. Split the text into a list of lines, preserving the visual structure
    lines = [line.strip() for line in search_text.split('\n') if line.strip()]
    
    results = []

    # 3. Read the resume line-by-line
    for i, line in enumerate(lines):
        
        # Check if the current line contains a degree keyword
        found_level = None
        for kw in valid_levels:
            pattern = r"(?i)\b(" + re.escape(kw) + r"\b(?:\s+[a-zA-Z]+){0,4})"
            match = re.search(pattern, line)
            
            if match:
                level_words = []
                for word in match.group(1).split():
                    if word.lower() in stop_words:
                        break
                    level_words.append(word)
                found_level = " ".join(level_words).title()
                break # Stop at the first valid degree found on this line
        
        # 4. If we found a degree, build a "mini-block" around it
        if found_level:
            # Usually, the university is on the line right above the degree
            start_idx = max(0, i - 1)
            
            # Look ahead up to 2 lines for the CGPA, but STOP if we hit another degree
            end_idx = i + 1
            while end_idx < len(lines) and end_idx <= i + 2:
                # Circuit Breaker: Does the next line contain a different degree?
                has_next_degree = any(
                    re.search(r"(?i)\b" + re.escape(k) + r"\b", lines[end_idx]) 
                    for k in valid_levels
                )
                if has_next_degree:
                    break # Hit a wall, stop expanding the block!
                end_idx += 1
            
            # Combine only these specific, safe lines into our search block
            block_text = " | ".join(lines[start_idx:end_idx])
            
            # 5. Extract University and CGPA *strictly* within this safe block
            found_uni = "Unknown Institution"
            uni_pattern = (
                r"(?i)\b((?:[a-zA-Z]+\s+){0,3}"
                r"(?:University|College|Institute|Politeknik|Universiti|School)"
                r"(?:\s+[a-zA-Z]+){0,3})\b"
            )
            uni_match = re.search(uni_pattern, block_text)
            if uni_match:
                uni_words = [
                    w for w in uni_match.group(1).split() 
                    if w.lower() not in stop_words
                ]
                found_uni = " ".join(uni_words).title()

            cgpa_match = re.search(r"(?i)(?:CGPA|GPA)[\s:\-]*([0-4]\.\d{1,2})", block_text)

            if not cgpa_match:
                cgpa_match = re.search(r"(?i)(?:CGPA|GPA)[\s:\-]*([0-4]\.\d{1,4})", edu_block)

            if not cgpa_match:
                cgpa_match = re.search(r"(?i)(?:CGPA|GPA|Academic Qualifications:\s*CGPA)[\s:\-]*([0-4]\.\d{1,4})", text)

            found_cgpa = cgpa_match.group(1) if cgpa_match else "N/A"
            
            # 6. Format and save
            entry = f"{found_uni} — {found_level} (CGPA: {found_cgpa})"
            
            # Prevent duplicates if the loop accidentally catches the same degree twice
            if not any(found_level in existing for existing in results):
                results.append(entry)

    return results if results else ["Education not clearly listed"]


def parse_resume(pdf_path: str) -> dict:
    text = extract_text(pdf_path)
    return {
        "name": extract_name(text),
        "email": extract_email(text),
        "phone": extract_phone(text),
        "skills": extract_skills(text),
        "education": extract_education(text),
    }
