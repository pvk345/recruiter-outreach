import os

from pypdf import PdfReader

import config
import email_generator
import storage


def extract_text(pdf_path):
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def process_resume():
    """Reads resumes/resume.pdf, extracts text, summarizes via OpenAI, and stores it.
    Returns the stored row, or None if no PDF exists yet at the fixed path."""
    pdf_path = config.RESUME_PDF_PATH
    if not os.path.isfile(pdf_path):
        return None

    raw_text = extract_text(pdf_path)
    summary = email_generator.summarize_resume(raw_text)
    storage.upsert_resume(raw_text, summary, pdf_path)
    return storage.get_resume()
