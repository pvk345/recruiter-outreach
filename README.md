# Recruiter Outreach Tool

Local tool: enter a company name, find tech recruiters via Apollo.io, draft personalized
outreach emails with OpenAI using your resume as context, review/edit each draft, and send
approved ones via your own Gmail account.

## Setup

1. Create a virtual environment and install dependencies:
   ```
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `APOLLO_API_KEY` — from your Apollo.io account (Settings > API).
   - `OPENAI_API_KEY` — from platform.openai.com.
   - Leave `TEST_SEND_MODE=true` and set `TEST_SEND_EMAIL` to your own address until you've
     verified the full pipeline.
3. Create a Google Cloud OAuth client (type: **Desktop app**), enable the Gmail API, download
   the credentials JSON, and save it as `client_secret.json` in the project root.
4. Run the app:
   ```
   python app.py
   ```
   Then open `http://localhost:5001` (note: 5001, not 5000 — macOS's AirPlay Receiver squats
   on port 5000 via `localhost`, so we moved off it; `127.0.0.1:5000` would technically also
   work, but 5001 avoids the confusion entirely).

## First run

1. Drop your resumes at `resumes/new_grad.pdf` and `resumes/internship.pdf` (either or both —
   whichever exist get processed). Fill in your LinkedIn and GitHub URLs on the Setup page.
   Click "(Re)process resumes" — each PDF is summarized once via OpenAI and reused for every
   email of that type, and the PDF itself is what gets attached to outreach emails.
2. Click "Connect Gmail" and complete the OAuth consent screen.
3. Search a company (choosing New Grad or Internship), review the generated drafts (each
   includes the matching resume PDF as an attachment and a signature with your LinkedIn/GitHub),
   edit as needed, and approve to send.

See `.env.example` for all configurable options (per-run email cap, test-send mode, etc).

## Future ideas (backlog, not built yet)

- Paste a job description and generate a tailored, ATS-friendly resume (LLM writes LaTeX from
  your structured profile data, compiled to PDF) to use as the attachment for that specific
  recruiter instead of your default resume.
