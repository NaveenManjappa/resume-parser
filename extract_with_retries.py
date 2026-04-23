import logging
import instructor
from google import genai

from config import GEMINI_API_KEY, GEMINI_MODEL
from schemas import CandidateProfile

# Turn on logging so we can SEE what instructor is doing
# DEBUG level reveals every LLM call, retry and validation error
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Silence some noisy libraries we don't care about
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)

client = genai.Client(api_key=GEMINI_API_KEY)
instructor_client = instructor.from_genai(client)

# A resume sample
# - No email address anywhere (will force validation failure on EmailStr)
# - Vague experience ("a few years")
# - Sparse data
HARD_RESUME = """
Alex
Software developer with a few years of experience.

Used Python and some cloud stuff at a previous job.
Contact me via LinkedIn.
"""

print("=" * 70)
print("ATTEMPTING EXTRACTION ON A DELIBERATELY HARD RESUME")
print("=" * 70)

try:
    profile = instructor_client.chat.completions.create(
        model=GEMINI_MODEL,
        response_model=CandidateProfile,
        max_retries=3,
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract a structured candidate profile from the following resume text. "
                    "Only use information explicitly present in the text. \n n"
                    f"RESUME:\n{HARD_RESUME}"
                ),
            }
        ],
    )
    print("\n" + "=" * 70)
    print("FINAL RESULT (extraction succeeded):")
    print("=" * 70)
    print(profile.model_dump_json(indent=2))

except Exception as e:
    print("\n" + "=" * 70)
    print(f"EXTRACTION FAILED AFTER RETRIES: {type(e).__name__}")
    print("=" * 70)
    print(str(e))
