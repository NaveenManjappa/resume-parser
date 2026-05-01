import logging
import time

import instructor
from google import genai
from instructor import Instructor

from api_models import ExtractResponse, ExtractResponseMetadata
from config import settings
from schemas import CandidateProfile

logger = logging.getLogger(__name__)


def create_instructor_client() -> Instructor:
    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return instructor.from_genai(gemini_client)


def extract_profile(resume_text: str, instructor_client: Instructor) -> ExtractResponse:
    # raise RuntimeError("deliberate test of 500 path")
    start = time.perf_counter()
    result = instructor_client.chat.completions.create_with_completion(
        model=settings.gemini_model,
        response_model=CandidateProfile,
        max_retries=settings.max_retries,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract a structured candidate profile from the following resume text. "
                    "Only use the information explicitly present in the text. \n\n "
                    f"Resume:\n {resume_text}"
                ),
            }
        ],
    )
    profile, completion = result
    elapsed_time = int((time.perf_counter() - start) * 1000)
    usage = getattr(completion, "usage_metadata", None)
    prompt_tokens = getattr(usage, "prompt_token_count", None) if usage else None
    completion_tokens = (
        getattr(usage, "candidates_token_count", None) if usage else None
    )

    metadata = ExtractResponseMetadata(
        model_used=settings.gemini_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        extraction_time_ms=elapsed_time,
    )

    logger.info(
        "Extraction complete: %d ms, prompt=%s, completion=%s",
        elapsed_time,
        prompt_tokens,
        completion_tokens,
    )
    return ExtractResponse(profile=profile, metadata=metadata)
