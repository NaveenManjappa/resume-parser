import os
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY=os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
  raise RuntimeError("GEMINI_API_KEY not found in the environment")

GEMINI_MODEL ="gemini-2.5-flash"