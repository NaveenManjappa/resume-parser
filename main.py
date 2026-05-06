import logging
from fastapi import FastAPI, HTTPException, Depends, Request, Header
from contextlib import asynccontextmanager
from pydantic import ValidationError
from instructor.core import InstructorRetryException
from instructor import Instructor
from api_models import ExtractRequest, ExtractResponse
from extraction_service import extract_profile, create_instructor_client
from config import settings
from azure.monitor.opentelemetry import configure_azure_monitor
import os
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger(__name__)

_app_insights_enabled = bool(os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"))

if _app_insights_enabled:
    configure_azure_monitor(logger_name=__name__)
    logger.info("Azure Monitor instrumentation enabled")
else:
    logger.info("Azure Monitor not configured (no connection string)")


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

if _app_insights_enabled:
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI auto-instrumentation enabled")


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if x_api_key != settings.app_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def get_instructor_client(request: Request) -> Instructor:
    return request.app.state.instructor_client


@app.post(
    "/api/v1/extract",
    response_model=ExtractResponse,
    dependencies=[Depends(require_api_key)],
)
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


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
