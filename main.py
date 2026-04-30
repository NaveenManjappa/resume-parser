import logging
from fastapi import FastAPI, HTTPException, Depends, Request
from contextlib import asynccontextmanager
from pydantic import ValidationError
from instructor.exceptions import InstructorRetryException
from instructor import Instructor
from api_models import ExtractRequest, ExtractResponse
from extraction_service import extract_profile, create_instructor_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        app.state.instructor_client = create_instructor_client()
        yield
    finally:
        # No explicit cleanup needed — the Gemini client uses an httpx pool
        # that's released when the process exits.
        logger.info("Application shutting down..")


app = FastAPI(title="Resume Parser API", version="0.1.0", lifespan=lifespan)


def get_instructor_client(request: Request) -> Instructor:
    return request.app.state.instructor_client


@app.post("/api/v1/extract", response_model=ExtractResponse)
def extract_text(
    request: ExtractRequest,
    instructor_client: Instructor = Depends(get_instructor_client),
) -> ExtractResponse:
    try:
        return extract_profile(request.resume_text, instructor_client)
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
