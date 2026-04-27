import logging
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
from instructor.exceptions import InstructorRetryException
from api_models import ExtractRequest, ExtractResponse
from extraction_service import extract_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = FastAPI(title="Resume Parser API", version="0.1.0")


@app.post("/api/v1/extract", response_model=ExtractResponse)
def extract_text(request: ExtractRequest) -> ExtractResponse:
    try:        
        return extract_profile(request.resume_text)
    except InstructorRetryException as e:
      logger.warning("Extraction failed after retries: %s", e)
      raise HTTPException(
        status_code=422,
        detail="Could not extract a structured profile from the provided resume.",
    )
    except ValidationError as e:
      logger.warning("Validation error during extraction: %s", e)
      raise HTTPException(
        status_code=422,
        detail="The extracted profile failed validation.",
    )
    except Exception:
      logger.exception("Unexpected error during extraction")
    raise HTTPException(
        status_code=500,
        detail="Internal error during extraction.",
    )
