from schemas import CandidateProfile
from pydantic import ValidationError

# Test 1 : valid input should succeed
valid = CandidateProfile(
  full_name="John Doe",
  email="john@examp.com",
  years_of_experience=8,
  skills=["Python","Azure","Fast API"],
  current_title="Senior AI Engineer"
)

print("Valid case passed",valid.model_dump_json(indent=2))

#Test 2: bad email should fail
try:
  CandidateProfile(
    full_name="Bad Email",
    email="not-an-email",
    years_of_experience=3,
    skills=["Python"],
    current_title="Enginner"
  )

except ValidationError as e:
  print("Invalid email rejected correctly")
  print(e)

#Test 3: out of range exeperience should fail
try:
  CandidateProfile(
    full_name="Mavan",
    email="mavan@example.com",
    years_of_experience=888,
    skills=["Azure"],
    current_title="Design Lead"
  )

except ValidationError as e:
  print("Out of range value for experience")
  print(e)