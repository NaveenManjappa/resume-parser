import logging
import time

import instructor
from google import genai
from instructor import Instructor
from instructor.core import InstructorRetryException
from pydantic import ValidationError

from api_models import ExtractResponse, ExtractResponseMetadata
from config import settings
from schemas import CandidateProfile
from opentelemetry import metrics

_meter = metrics.get_meter("resume-parser")

_extraction_duration_ms = _meter.create_histogram(
    name="extraction.duration_ms",
    unit="ms",
    description="Wall-clock duration of extract profile",
)

_extraction_prompt_tokens = _meter.create_histogram(
    name="extraction.prompt_tokens",
    unit="tokens",
    description="Prompt tokens used per extraction",
)

_extraction_completion_tokens = _meter.create_histogram(
    name="extraction.completion_tokens",
    unit="tokens",
    description="Completion tokens used per extraction",
)

_extraction_failures = _meter.create_counter(
    name="extraction.failures",
    unit="1",
    description="Count of failed extractions (post-retry)",
)

logger = logging.getLogger(__name__)


def create_instructor_client() -> Instructor:
    gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return instructor.from_genai(gemini_client)


def extract_profile(resume_text: str, instructor_client: Instructor) -> ExtractResponse:
    # raise RuntimeError("deliberate test of 500 path")
    attrs = {"model": settings.gemini_model}
    try:
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

        _extraction_duration_ms.record(
            elapsed_time, attributes={**attrs, "status": "success"}
        )
        if prompt_tokens is not None:
            _extraction_prompt_tokens.record(prompt_tokens, attributes=attrs)

        if completion_tokens is not None:
            _extraction_completion_tokens.record(completion_tokens, attributes=attrs)

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
    except InstructorRetryException:
        elapsed_time = int((time.perf_counter() - start) * 1000)
        _extraction_duration_ms.record(
            elapsed_time, attributes={**attrs, "status": "retry_exhausted"}
        )

        _extraction_failures.add(1, attributes={**attrs, "reason": "retry_exhausted"})
        raise
    except ValidationError:
        _extraction_failures.add(1, attributes={**attrs, "reason": "validation"})
        raise
