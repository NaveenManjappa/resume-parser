from schemas import CandidateProfile
from pydantic import ValidationError

# Test 1: A "complete" resume - all fields populated
print("--- Test 1: complete profile ---")
complete = CandidateProfile(
    full_name="Jane Doe",
    email="jane@example.com",
    years_of_experience=8,
    years_of_experience_source="explicit_dates",
    skills=["Python", "FastAPI"],
    current_title="Senior Engineer",
)
print("Passed")
print(complete.model_dump_json(indent=2))

# Test 2: A sparse resume - only the truly required field
print("\n--- Test 2: sparse profile (only full_name + source) ---")
sparse = CandidateProfile(
    full_name="Alex",
    years_of_experience_source="unknown",
)
print("Passed")
print(sparse.model_dump_json(indent=2))

# Test 3: full_name is still required - this MUST fail
print("\n--- Test 3: missing full_name should fail ---")
try:
    CandidateProfile(
        full_name="",
        years_of_experience_source="unknown"
    )
    print("Should have failed!")
except ValidationError as e:
    print("Correctly rejected missing full_name")

# Test 4: invalid Literal value should fail
print("\n--- Test 4: invalid source enum should fail ---")
try:
    CandidateProfile(
        full_name="Test",
        years_of_experience_source="from_my_intuition",  # not a valid Literal
    )
    print("❌ Should have failed!")
except ValidationError as e:
    print("✅ Correctly rejected invalid Literal value")