import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    full_name TEXT,
    linkedin_url TEXT,
    github_url TEXT,
    portfolio_url TEXT,
    email_template TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resumes (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    raw_text TEXT,
    summary TEXT,
    resume_pdf_path TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS org_search_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    apollo_org_id TEXT NOT NULL,
    name TEXT NOT NULL,
    domain TEXT,
    website_url TEXT,
    linkedin_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_org_search_cache_query ON org_search_cache(query);

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apollo_org_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recruiters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apollo_person_id TEXT NOT NULL UNIQUE,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    name TEXT,
    title TEXT,
    linkedin_url TEXT,
    email TEXT,
    is_university_recruiter INTEGER NOT NULL DEFAULT 0,
    is_technical_recruiter INTEGER NOT NULL DEFAULT 0,
    enriched_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES runs(id),
    recruiter_id INTEGER NOT NULL REFERENCES recruiters(id),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'skipped', 'sent')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TEXT,
    gmail_message_id TEXT
);
"""


@contextmanager
def _connect():
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with _connect() as conn:
        conn.executescript(SCHEMA)
        try:
            conn.execute("ALTER TABLE companies ADD COLUMN research_summary TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists


# --- profile (linkedin/github/portfolio, shared across all outreach) ---

def get_profile():
    with _connect() as conn:
        return conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()


def upsert_profile(full_name, linkedin_url, github_url, portfolio_url):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, full_name, linkedin_url, github_url, portfolio_url)
            VALUES (1, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                full_name = excluded.full_name,
                linkedin_url = excluded.linkedin_url,
                github_url = excluded.github_url,
                portfolio_url = excluded.portfolio_url
            """,
            (full_name, linkedin_url, github_url, portfolio_url),
        )


def update_email_template(email_template):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO profile (id, email_template)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET email_template = excluded.email_template
            """,
            (email_template,),
        )


# --- resume (single row) ---

def get_resume():
    with _connect() as conn:
        return conn.execute("SELECT * FROM resumes WHERE id = 1").fetchone()


def upsert_resume(raw_text, summary, resume_pdf_path):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO resumes (id, raw_text, summary, resume_pdf_path)
            VALUES (1, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                raw_text = excluded.raw_text,
                summary = excluded.summary,
                resume_pdf_path = excluded.resume_pdf_path,
                created_at = CURRENT_TIMESTAMP
            """,
            (raw_text, summary, resume_pdf_path),
        )


# --- org search cache (raw candidate list per typed query, so repeat searches of the same
# term never re-call Apollo's org search even when disambiguation is shown again) ---

def _normalize_query(query):
    return query.strip().lower()


def get_cached_org_candidates(query):
    """Returns the cached candidate list for this query, or None if never searched before."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM org_search_cache WHERE query = ? ORDER BY id ASC",
            (_normalize_query(query),),
        ).fetchall()
        return rows if rows else None


def cache_org_search(query, candidates):
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO org_search_cache (query, apollo_org_id, name, domain, website_url, linkedin_url)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (_normalize_query(query), c["apollo_org_id"], c["name"], c.get("domain"), c.get("website_url"), c.get("linkedin_url"))
                for c in candidates
            ],
        )


# --- companies (one row per resolved Apollo organization, keyed by apollo_org_id) ---

def get_company_by_org_id(apollo_org_id):
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM companies WHERE apollo_org_id = ?", (apollo_org_id,)
        ).fetchone()


def get_or_create_company(apollo_org_id, name):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO companies (apollo_org_id, name) VALUES (?, ?) ON CONFLICT(apollo_org_id) DO NOTHING",
            (apollo_org_id, name),
        )
        return conn.execute(
            "SELECT * FROM companies WHERE apollo_org_id = ?", (apollo_org_id,)
        ).fetchone()


def get_company(company_id):
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM companies WHERE id = ?", (company_id,)
        ).fetchone()


def set_company_research(company_id, research_summary):
    with _connect() as conn:
        conn.execute(
            "UPDATE companies SET research_summary = ? WHERE id = ?",
            (research_summary, company_id),
        )


# --- recruiters (enrichment cache keyed by Apollo person id) ---

def get_recruiter(recruiter_id):
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM recruiters WHERE id = ?", (recruiter_id,)
        ).fetchone()


def get_recruiter_by_apollo_id(apollo_person_id):
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM recruiters WHERE apollo_person_id = ?", (apollo_person_id,)
        ).fetchone()


def upsert_recruiter(apollo_person_id, company_id, name, title, linkedin_url, is_university_recruiter, is_technical_recruiter):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO recruiters (apollo_person_id, company_id, name, title, linkedin_url, is_university_recruiter, is_technical_recruiter)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(apollo_person_id) DO UPDATE SET
                name = excluded.name,
                title = excluded.title,
                linkedin_url = excluded.linkedin_url,
                is_university_recruiter = excluded.is_university_recruiter,
                is_technical_recruiter = excluded.is_technical_recruiter
            """,
            (apollo_person_id, company_id, name, title, linkedin_url, int(is_university_recruiter), int(is_technical_recruiter)),
        )
        return conn.execute(
            "SELECT * FROM recruiters WHERE apollo_person_id = ?", (apollo_person_id,)
        ).fetchone()


def list_recruiters_for_company(company_id):
    with _connect() as conn:
        return conn.execute(
            """
            SELECT * FROM recruiters
            WHERE company_id = ? AND email IS NOT NULL
            ORDER BY is_university_recruiter DESC, is_technical_recruiter DESC, name ASC
            """,
            (company_id,),
        ).fetchall()


def set_recruiter_email(apollo_person_id, email):
    with _connect() as conn:
        conn.execute(
            "UPDATE recruiters SET email = ?, enriched_at = CURRENT_TIMESTAMP WHERE apollo_person_id = ?",
            (email, apollo_person_id),
        )


def recruiter_has_sent_draft(recruiter_id):
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM drafts WHERE recruiter_id = ? AND status = 'sent' LIMIT 1",
            (recruiter_id,),
        ).fetchone()
        return row is not None


# --- runs (one per batch draft-generation action) ---

def create_run(company_id):
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO runs (company_id) VALUES (?)",
            (company_id,),
        )
        return cur.lastrowid


def get_run(run_id):
    with _connect() as conn:
        return conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()


# --- drafts (the review queue) ---

def get_last_sent_at():
    """UTC timestamp string of the most recent successful send, or None if none yet."""
    with _connect() as conn:
        row = conn.execute("SELECT MAX(sent_at) FROM drafts WHERE status = 'sent'").fetchone()
        return row[0] if row else None


def create_draft(run_id, recruiter_id, subject, body):
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO drafts (run_id, recruiter_id, subject, body) VALUES (?, ?, ?, ?)",
            (run_id, recruiter_id, subject, body),
        )
        return cur.lastrowid


def get_draft(draft_id):
    with _connect() as conn:
        return conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()


def get_latest_draft_for_recruiter(recruiter_id):
    """Most recent draft for this recruiter (any status), or None if never drafted."""
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM drafts WHERE recruiter_id = ? ORDER BY id DESC LIMIT 1",
            (recruiter_id,),
        ).fetchone()


def update_draft(draft_id, subject, body):
    with _connect() as conn:
        conn.execute(
            "UPDATE drafts SET subject = ?, body = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
            (subject, body, draft_id),
        )


def list_drafts_for_run(run_id):
    with _connect() as conn:
        return conn.execute(
            """
            SELECT drafts.*, recruiters.name AS recruiter_name, recruiters.title AS recruiter_title,
                   recruiters.email AS recruiter_email, recruiters.is_university_recruiter
            FROM drafts
            JOIN recruiters ON recruiters.id = drafts.recruiter_id
            WHERE drafts.run_id = ?
            ORDER BY recruiters.is_university_recruiter DESC, drafts.id ASC
            """,
            (run_id,),
        ).fetchall()


def mark_draft_sent(draft_id, subject, body, gmail_message_id):
    """Conditional on status='pending' so a double-submitted approve click can't send twice."""
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE drafts
            SET status = 'sent', subject = ?, body = ?, gmail_message_id = ?,
                sent_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'pending'
            """,
            (subject, body, gmail_message_id, draft_id),
        )
        return cur.rowcount == 1


def mark_draft_skipped(draft_id):
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE drafts SET status = 'skipped', updated_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
            (draft_id,),
        )
        return cur.rowcount == 1


def revert_draft_to_pending(draft_id):
    """Undoes a 'sent' marking (e.g. after a bounce) so the draft can be edited/resent.
    Conditional on status='sent' so this can't be used to un-skip a draft."""
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE drafts
            SET status = 'pending', sent_at = NULL, gmail_message_id = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'sent'
            """,
            (draft_id,),
        )
        return cur.rowcount == 1


init_db()
