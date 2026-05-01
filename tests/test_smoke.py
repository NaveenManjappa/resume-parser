from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

def test_settings_load_from_env():
    """Settings module imports and validates without error
    If GEMINI_API_KEY is missing from env, this fails
    """
    from config import settings

    assert settings.gemini_api_key, "GEMINI_API_KEY must be set in the environment"
    assert settings.gemini_model.startswith("gemini-")
    assert 0 <= settings.max_retries <= 10

def test_schema_rejects_invalid_email():
    from schemas import CandidateProfile
    with pytest.raises(ValidationError):
        CandidateProfile(
            full_name="Test",
            email="not-an-email",
            years_of_experience_source="unknown"
        )

def test_extract_endpoint_rejects_short_input():
    from main import app
    with TestClient(app) as client:
      response = client.post("/api/v1/extract",json={"resume_text":""})
      assert response.status_code == 422
      assert "detail" in response.json()
