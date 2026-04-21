from pydantic import BaseModel, EmailStr, Field, HttpUrl
from typing import Optional


class CandidateProfile(BaseModel):
    """A structured profile extracted from a candidate's resume.

    Used to convert unstructured resume text into a normalized,
    validated JSON object suitable for downstream processing
    (database storage, search indexing, ATS integration).
    """

    full_name: str = Field(
        ...,
        description="The candidate's full legal name as it appears at the top of the resume.",
    )
    email: EmailStr = Field(
        ...,
        description="The candidate's primary contact email address.",
    )
    years_of_experience: int = Field(
        ...,
        ge=0,
        le=70,
        description=(
            "Total years of professional work experience. " 
            "Calculate from the earliest job start date to the most recent end date (or present). " 
            "Exclude internships and academic projects." 
        ),
    )
    skills: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description=(
            "A list of technical skills, programming languages, frameworks, and tools. " 
            "Exclude soft skills (e.g., 'communication', 'teamwork', 'leadership')." 
        ),
    )
    current_title: str = Field(
        ...,
        description="The candidate's most recent job title, taken from the topmost or most recent role in the work history.",
    )
    summary: str | None = Field(
        default=None,
        description=(
            "A brief professional summary, only if one is explicitly present in the resume " 
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
