from pydantic import BaseModel, Field

from schemas import CandidateProfile


class ExtractRequest(BaseModel):
    resume_text: str = Field(
        ...,
        min_length=100,
        max_length=20000,
        description="The raw text content of candidate's resume",
    )


class ExtractResponseMetadata(BaseModel):
    model_used: str
    extraction_time_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ExtractResponse(BaseModel):
    profile: CandidateProfile
    metadata: ExtractResponseMetadata
