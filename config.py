import os

from dotenv import load_dotenv

load_dotenv()

APOLLO_API_KEY = os.environ["APOLLO_API_KEY"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

GMAIL_CLIENT_SECRET_PATH = os.getenv("GMAIL_CLIENT_SECRET_PATH", "client_secret.json")
GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "data/token.json")

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/app.db")

RESUME_DIR = os.getenv("RESUME_DIR", "resumes")
CANDIDATE_NAME = os.getenv("CANDIDATE_NAME", "Candidate")
RESUME_PDF_PATH = os.path.join(RESUME_DIR, f"{CANDIDATE_NAME}Resume.pdf")

MAX_EMAILS_PER_RUN = int(os.getenv("MAX_EMAILS_PER_RUN", "10"))
TEST_SEND_MODE = os.getenv("TEST_SEND_MODE", "true").strip().lower() == "true"
TEST_SEND_EMAIL = os.getenv("TEST_SEND_EMAIL", "")

# Required delay between sends, enforced server-side, is randomized within this range each
# time -- a perfectly uniform gap is itself a bot-like pattern, so we vary it -- to avoid
# tripping Gmail's spam/abuse heuristics (send bursts are a strong signal even well under the
# daily quota).
SEND_DELAY_MIN_SECONDS = int(os.getenv("SEND_DELAY_MIN_SECONDS", "60"))
SEND_DELAY_MAX_SECONDS = int(os.getenv("SEND_DELAY_MAX_SECONDS", "120"))

# Apollo person_locations filter -- hard-restricts people search results to these locations
# so outreach only targets recruiters who can actually hire for US-based roles.
RECRUITER_LOCATIONS = ["United States"]

# Recruiting-related job titles used to filter Apollo people-search results.
RECRUITER_TITLES = [
    "recruiter",
    "technical recruiter",
    "university recruiter",
    "university recruiting",
    "campus recruiter",
    "campus recruiting",
    "early career recruiter",
    "early talent",
    "new grad recruiter",
    "talent acquisition",
]

# Substrings checked against a recruiter's title to flag them as a university/early-career
# recruiter (surfaced first in the review queue, since they're the highest-value contact for
# new-grad outreach).
UNIVERSITY_RECRUITER_KEYWORDS = [
    "university",
    "campus",
    "early career",
    "early talent",
    "new grad",
]

# Substrings checked against a recruiter's title to flag them as a technical recruiter
# (surfaced first, since they're more likely to actually hire for SWE roles than a
# generalist recruiter).
TECHNICAL_RECRUITER_KEYWORDS = [
    "technical",
    "engineering",
    "software",
    "swe",
    "tech ",
]

os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
os.makedirs(os.path.dirname(GMAIL_TOKEN_PATH) or ".", exist_ok=True)
