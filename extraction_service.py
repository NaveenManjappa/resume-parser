from api_models import ExtractResponse, ExtractResponseMetadata
import instructor
from google import genai
from schemas import CandidateProfile
import time
import logging
from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)
_gemini_client = genai.Client(api_key=GEMINI_API_KEY)
_instructor_client = instructor.from_genai(_gemini_client)

def extract_profile(resume_text: str) -> ExtractResponse:
    start = time.perf_counter()
    result = _instructor_client.chat.completions.create_with_completion(
        model=GEMINI_MODEL,
        response_model=CandidateProfile,
        max_retries=3,
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
        model_used=GEMINI_MODEL,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        extraction_time_ms=elapsed_time,
    )

    logger.info(
        "Extraction complete: %d ms,prompt=%s,completion=%s",
        elapsed_time,
        prompt_tokens,
        completion_tokens,
    )
    return ExtractResponse(profile=profile, metadata=metadata)
