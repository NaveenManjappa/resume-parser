import instructor
from google import genai

from config import GEMINI_API_KEY,GEMINI_MODEL
from schemas import CandidateProfile

#Step 1 Create the Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

#Step 2 Wrap it with instructor
instructor_client = instructor.from_genai(client)

#Step 3 A sample resume
SAMPLE_RESUME = """
Jane Doe
jane.doe@example.com

Senior Software Engineer with 7 years of experience building web applications.

EXPERIENCE
Senior Software Engineer, Acme Corp (2021-Present)
- Led migration of legacy monolith to microservices on Azure
- Mentored team of 4 junior engineers

Software Engineer, Beta Inc (2017-2021)
- Built internal tools with Python, FastAPI, and React

SKILLS
Python, FastAPI, Azure, Docker, Kubernetes, PostgreSQL, React, TypeScript
"""
#Step 4 Extract call
profile = instructor_client.chat.completions.create(
  model=GEMINI_MODEL,
  response_model=CandidateProfile,
  messages=[
    {
      "role":"user",
      "content":(
        "Extract a structured candidate profile from the following resume text" 
        "Only use information explicitly present in the text. \n\n" 
        f"RESUME:\n{SAMPLE_RESUME}"
      )
    }
  ]
)

print(profile.model_dump_json(indent=2))
print(f"\nType of result: {type(profile).__name__}")

print(profile.skills[0])
