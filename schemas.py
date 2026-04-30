from pydantic import BaseModel, EmailStr, Field, HttpUrl
from typing import Literal


class CandidateProfile(BaseModel):
    """A structured profile extracted from a candidate's resume.

     Used to convert unstructured resume text into a normalized,
    validated JSON object suitable for downstream processing
    (database storage, search indexing, ATS integration).

    Design principle: this schema describes what resume data CAN be,
    not what we wish it would be. Business rules about which fields
    are 'acceptable as missing' live in the application layer, not here.
    """

    full_name: str = Field(
        ...,
        #min_length=600,
        description=(
            "The candidate's full legal name as it appears at the top of the resume. "
            "If no name can be identified, the resume is malformed and extraction should fail."
        ),
    )
    email: EmailStr | None = Field(
        default=None,
        description=(
            "The candidate's primary contact email address. "
            "Return null if no valid email is explicitly present in the source text. "
            "Do not invent or construct an email from the candidate's name or company"
        ),
    )
    years_of_experience: int | None = Field(
        default=None,
        ge=0,
        le=70,
        description=(
            "Total years of professional work experience. "
            "Calculate from the explicit start/end dates in the work history when available. "
            "If only stated summary like '7 years' is present without verifiable dates,use that. "
            "Return null if neither explicit dates nor an explicit statement of experience can be found. "
            "Do not estimate or infer based on perceived seniority of job titles."
        ),
    )
    years_of_experience_source: Literal[
        "explicit_dates", "stated_summary", "unknown"
    ] = Field(
        ...,
        description=(
            "How years of experience was derived or calculated. "
            "Use 'explicit_dates' when calculated from start/end dates in the work history. "
            "Use 'stated_summary' when taken from an explicit statement like 'X years of experience'. "
            "Use 'unknown' when years_of_experiece is null"
        ),
    )

    skills: list[str] = Field(
        default_factory=list,
        max_length=50,
        description=(
            "A list of explicitly mentioned technical skills, programming languages, frameworks, and tools. Use the exact terms as they appear in the resume - do not paraphrase, normalize or infer skills from project descriptions.  "
            "Exclude soft skills (e.g., 'communication', 'teamwork', 'leadership')."
        ),
    )
    current_title: str | None = Field(
        default=None,
        description=(
            "The candidate's most recent role by date, regardless of the resume layout.   "
            "Return null if the resume only lists projects without roles, if the candidate is a student with no formal job titles, or if no clear current/most recent title can be identified. "
            "Do not infer a title from the project descriptions or technical skills(e.g., do not output 'Python Developer' just because Python skills are present)."
        ),
    )
    summary: str | None = Field(
        default=None,
        description=(
            "A brief professional summary, only if one is explicitly present in the resume. "
            "(typically in a 'Summary' or 'Profile' section near the top). "
            "Do not synthesize a summary if none exists in the source text."
        ),
    )
    linkedin_url: HttpUrl | None = Field(
        default=None,
        description=(
            "The candidate's LinkedIn profile URL, if explicitly present in the resume. "
            "Must be a full URL starting with 'https://' (typically https://linkedin.com/in/...). "
            "Return null if no LinkedIn URL is present — do not guess or construct a URL from the candidate's name."
        ),
    )
