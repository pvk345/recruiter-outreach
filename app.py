import random
from datetime import datetime, timedelta, timezone

from flask import Flask, flash, redirect, render_template, request, session, url_for

import apollo_client
import company_research
import config
import email_generator
import gmail_client
import resume as resume_module
import storage


def _get_or_research_company(company, resume_summary):
    """Returns cached research notes for this company, or runs the LangChain research agent
    once (grounded in the candidate's resume, so it can search for ties to their specific
    background) and caches the result. Falls back to None (general-knowledge mode) if the
    agent errors out, rather than blocking draft generation."""
    if company["research_summary"]:
        return company["research_summary"]
    try:
        research_notes = company_research.research_company(company["name"], resume_summary)
    except Exception:
        return None
    storage.set_company_research(company["id"], research_notes)
    return research_notes

app = Flask(__name__)
app.secret_key = "dev-only-local-app-not-served-publicly"

DEFAULT_EMAIL_TEMPLATE = """\
My name is Prateek Komarla, 
and I'm a Computer Science and Data Science student at Rutgers University, graduating in May 2028. 
I'm reaching out to inquire about any Software Engineering internship or new graduate opportunities at  {company_name}.

{company_interest}

I most recently interned as a Software Engineer at Astralinx, where I built a Spring Boot backend with RESTful APIs for a business-writing suggestion platform, optimized query performance to cut API response time by 35%, and built the interactive TypeScript frontend with real-time NLP-powered suggestions. I'm also currently a Research Assistant at Rutgers, building a convolutional neural network to automate wound-progression image analysis for cell biology experiments.

Outside of coursework, I've built a few end-to-end AI/ML projects: DataChat, an AI data analyst that lets users query CSVs in plain English through a LangChain agent and auto-generates PDF business reports; a U-Net image segmentation model built from scratch in TensorFlow/Keras; and ClimateShield, a full-stack platform that scores wildfire and flood risk for any US address using a custom XGBoost model, deployed on AWS Lambda.

I've attached my resume and would greatly appreciate it if you could let me know if there are any opportunities that align with my background. If you're not the right person to contact, I'd be grateful if you could point me toward the appropriate recruiter or hiring manager.
Thank you for your time, and I look forward to hearing from you."""


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/setup")
def setup():
    return render_template(
        "setup_resume.html",
        profile=storage.get_profile(),
        resume=storage.get_resume(),
        resume_pdf_path=config.RESUME_PDF_PATH,
        default_email_template=DEFAULT_EMAIL_TEMPLATE,
        gmail_connected=gmail_client.is_connected(),
        test_send_mode=config.TEST_SEND_MODE,
        test_send_email=config.TEST_SEND_EMAIL,
    )


@app.route("/setup/email-template", methods=["POST"])
def setup_email_template():
    email_template = request.form.get("email_template", "").strip()
    try:
        email_template.format(company_name="Acme", company_interest="placeholder sentence")
    except (KeyError, IndexError) as exc:
        flash(f"Email template has an invalid placeholder: {exc}. Only {{company_name}} and {{company_interest}} are supported.", "error")
        return redirect(url_for("setup"))

    storage.update_email_template(email_template)
    flash("Email template saved.", "success")
    return redirect(url_for("setup"))


@app.route("/gmail/connect")
def gmail_connect():
    redirect_uri = url_for("gmail_callback", _external=True)
    auth_url, state, code_verifier = gmail_client.get_authorization_url(redirect_uri)
    session["gmail_oauth_state"] = state
    session["gmail_oauth_code_verifier"] = code_verifier
    return redirect(auth_url)


@app.route("/gmail/callback")
def gmail_callback():
    state = session.pop("gmail_oauth_state", None)
    code_verifier = session.pop("gmail_oauth_code_verifier", None)
    redirect_uri = url_for("gmail_callback", _external=True)
    try:
        gmail_client.exchange_code(redirect_uri, request.url, state, code_verifier)
        flash("Gmail connected.", "success")
    except Exception as exc:
        flash(f"Gmail connection failed: {exc}", "error")
    return redirect(url_for("setup"))


@app.route("/setup/profile", methods=["POST"])
def setup_profile():
    storage.upsert_profile(
        request.form.get("full_name", "").strip(),
        request.form.get("linkedin_url", "").strip(),
        request.form.get("github_url", "").strip(),
        request.form.get("portfolio_url", "").strip(),
    )
    flash("Profile saved.", "success")
    return redirect(url_for("setup"))


@app.route("/setup/resume/process", methods=["POST"])
def setup_resume_process():
    resume_row = resume_module.process_resume()
    if resume_row is None:
        flash(f"No resume found at {config.RESUME_PDF_PATH}.", "error")
    else:
        flash("Resume processed.", "success")
    return redirect(url_for("setup"))


@app.route("/search", methods=["POST"])
def search():
    company_name = request.form.get("company_name", "").strip()
    if not company_name:
        flash("Enter a company name.", "error")
        return redirect(url_for("index"))

    candidates = storage.get_cached_org_candidates(company_name)
    if candidates is None:
        candidates = apollo_client.search_organizations(company_name, per_page=5)
        if not candidates:
            flash(f'No Apollo organization found for "{company_name}".', "error")
            return redirect(url_for("index"))
        storage.cache_org_search(company_name, candidates)

    if len(candidates) == 1:
        candidate = candidates[0]
        company = storage.get_or_create_company(candidate["apollo_org_id"], candidate["name"])
        return redirect(url_for("run_company_search", company_id=company["id"]))

    return render_template("confirm_company.html", company_name=company_name, candidates=candidates)


@app.route("/search/confirm", methods=["POST"])
def search_confirm():
    org_id = request.form.get("org_id", "").strip()
    org_name = request.form.get("org_name", "").strip()
    if not org_id or not org_name:
        flash("Company selection missing, try searching again.", "error")
        return redirect(url_for("index"))

    company = storage.get_or_create_company(org_id, org_name)
    return redirect(url_for("run_company_search", company_id=company["id"]))


@app.route("/companies/<int:company_id>/run-search")
def run_company_search(company_id):
    company = storage.get_company(company_id)
    if not company:
        flash("Unknown company.", "error")
        return redirect(url_for("index"))

    if storage.list_recruiters_for_company(company_id):
        return redirect(url_for("company_recruiters", company_id=company_id))

    candidates = apollo_client.search_people(company["apollo_org_id"])
    candidates.sort(
        key=lambda c: (
            apollo_client.is_university_recruiter(c["title"]),
            apollo_client.is_technical_recruiter(c["title"]),
        ),
        reverse=True,
    )

    for candidate in candidates[: config.MAX_EMAILS_PER_RUN]:
        existing = storage.get_recruiter_by_apollo_id(candidate["id"])
        if existing and existing["email"]:
            continue

        enriched = apollo_client.enrich_person(candidate["id"])
        if not enriched:
            continue

        is_university = apollo_client.is_university_recruiter(enriched["title"])
        is_technical = apollo_client.is_technical_recruiter(enriched["title"])
        storage.upsert_recruiter(
            enriched["id"],
            company_id,
            enriched["name"],
            enriched["title"],
            enriched["linkedin_url"],
            is_university,
            is_technical,
        )
        storage.set_recruiter_email(enriched["id"], enriched["email"])

    return redirect(url_for("company_recruiters", company_id=company_id))


@app.route("/companies/<int:company_id>/recruiters")
def company_recruiters(company_id):
    company = storage.get_company(company_id)
    if not company:
        flash("Unknown company.", "error")
        return redirect(url_for("index"))

    recruiters = storage.list_recruiters_for_company(company_id)
    drafts_by_recruiter = {r["id"]: storage.get_latest_draft_for_recruiter(r["id"]) for r in recruiters}
    test_send_note = f" (TEST MODE: will actually go to {config.TEST_SEND_EMAIL})" if config.TEST_SEND_MODE else ""
    return render_template(
        "company_recruiters.html",
        company=company,
        recruiters=recruiters,
        drafts_by_recruiter=drafts_by_recruiter,
        test_send_mode=config.TEST_SEND_MODE,
        test_send_email=config.TEST_SEND_EMAIL,
        test_send_note=test_send_note,
    )


def _build_signature(profile):
    lines = [profile["full_name"]]
    if profile["linkedin_url"]:
        lines.append(f"LinkedIn: {profile['linkedin_url']}")
    if profile["github_url"]:
        lines.append(f"GitHub: {profile['github_url']}")
    if profile["portfolio_url"]:
        lines.append(f"Portfolio: {profile['portfolio_url']}")
    return "\n".join(lines)


def _compose_draft(body, recruiter, profile):
    first_name = (recruiter["name"] or "").split(" ")[0] or "there"
    full_body = f"Hi {first_name},\n\n{body}\n\nBest,\n{_build_signature(profile)}"
    subject = f"Software Engineering Opportunities — {profile['full_name']}"
    return subject, full_body


@app.route("/companies/<int:company_id>/drafts/generate", methods=["POST"])
def generate_drafts(company_id):
    company = storage.get_company(company_id)
    if not company:
        flash("Unknown company.", "error")
        return redirect(url_for("index"))

    recruiter_ids = request.form.getlist("recruiter_ids")
    if not recruiter_ids:
        flash("Select at least one recruiter.", "error")
        return redirect(url_for("company_recruiters", company_id=company_id))

    resume_row = storage.get_resume()
    if not resume_row or not resume_row["summary"]:
        flash("Process your resume in Setup before generating drafts.", "error")
        return redirect(url_for("company_recruiters", company_id=company_id))

    profile = storage.get_profile()
    if not profile or not profile["full_name"]:
        flash("Fill in your name in Setup before generating drafts.", "error")
        return redirect(url_for("company_recruiters", company_id=company_id))
    if not profile["email_template"]:
        flash("Fill in your email template in Setup before generating drafts.", "error")
        return redirect(url_for("company_recruiters", company_id=company_id))

    research_notes = _get_or_research_company(company, resume_row["summary"])

    generated = []
    try:
        for rid in recruiter_ids:
            recruiter = storage.get_recruiter(int(rid))
            if not recruiter:
                continue
            sentence = email_generator.company_interest_sentence(resume_row["summary"], company["name"], research_notes)
            body = profile["email_template"].format(company_name=company["name"], company_interest=sentence)
            subject, full_body = _compose_draft(body, recruiter, profile)
            generated.append((recruiter["id"], subject, full_body))
    except Exception as exc:
        flash(f"Draft generation failed, no drafts were created: {exc}", "error")
        return redirect(url_for("company_recruiters", company_id=company_id))

    run_id = storage.create_run(company_id)
    for recruiter_id, subject, full_body in generated:
        storage.create_draft(run_id, recruiter_id, subject, full_body)

    flash(f"Generated {len(generated)} draft(s).", "success")
    return redirect(url_for("company_recruiters", company_id=company_id))


@app.route("/drafts/<int:draft_id>/edit", methods=["POST"])
def edit_draft(draft_id):
    draft = storage.get_draft(draft_id)
    if not draft:
        flash("Unknown draft.", "error")
        return redirect(url_for("index"))

    storage.update_draft(draft_id, request.form.get("subject", "").strip(), request.form.get("body", "").strip())
    flash("Draft saved.", "success")
    recruiter = storage.get_recruiter(draft["recruiter_id"])
    return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))


@app.route("/drafts/<int:draft_id>/skip", methods=["POST"])
def skip_draft(draft_id):
    draft = storage.get_draft(draft_id)
    if not draft:
        flash("Unknown draft.", "error")
        return redirect(url_for("index"))

    storage.mark_draft_skipped(draft_id)
    recruiter = storage.get_recruiter(draft["recruiter_id"])
    return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))


@app.route("/drafts/<int:draft_id>/revert", methods=["POST"])
def revert_draft(draft_id):
    draft = storage.get_draft(draft_id)
    if not draft:
        flash("Unknown draft.", "error")
        return redirect(url_for("index"))

    recruiter = storage.get_recruiter(draft["recruiter_id"])
    if storage.revert_draft_to_pending(draft_id):
        flash("Reverted to pending -- editable and resendable again.", "success")
    else:
        flash("Draft wasn't marked sent, nothing to revert.", "error")
    return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))


@app.route("/drafts/<int:draft_id>/regenerate", methods=["POST"])
def regenerate_draft(draft_id):
    draft = storage.get_draft(draft_id)
    if not draft:
        flash("Unknown draft.", "error")
        return redirect(url_for("index"))

    recruiter = storage.get_recruiter(draft["recruiter_id"])
    company = storage.get_company(recruiter["company_id"])
    resume_row = storage.get_resume()
    profile = storage.get_profile()

    try:
        research_notes = _get_or_research_company(company, resume_row["summary"])
        sentence = email_generator.company_interest_sentence(resume_row["summary"], company["name"], research_notes)
        body = profile["email_template"].format(company_name=company["name"], company_interest=sentence)
    except Exception as exc:
        flash(f"Regeneration failed: {exc}", "error")
        return redirect(url_for("company_recruiters", company_id=company["id"]))

    subject, full_body = _compose_draft(body, recruiter, profile)
    storage.update_draft(draft_id, subject, full_body)
    flash("Draft regenerated.", "success")
    return redirect(url_for("company_recruiters", company_id=company["id"]))


@app.route("/drafts/<int:draft_id>/send", methods=["POST"])
def send_draft(draft_id):
    draft = storage.get_draft(draft_id)
    if not draft:
        flash("Unknown draft.", "error")
        return redirect(url_for("index"))

    recruiter = storage.get_recruiter(draft["recruiter_id"])
    if draft["status"] != "pending":
        flash("Draft was already sent or skipped.", "error")
        return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))

    last_sent_at = storage.get_last_sent_at()
    if last_sent_at:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        elapsed = now_utc - datetime.strptime(last_sent_at, "%Y-%m-%d %H:%M:%S")
        required_delay = random.uniform(config.SEND_DELAY_MIN_SECONDS, config.SEND_DELAY_MAX_SECONDS)
        remaining = timedelta(seconds=required_delay) - elapsed
        if remaining.total_seconds() > 0:
            flash(
                f"Please wait {int(remaining.total_seconds()) + 1} more second(s) before sending the next "
                f"email (randomized {config.SEND_DELAY_MIN_SECONDS}-{config.SEND_DELAY_MAX_SECONDS}s pacing "
                f"enforced to protect your account's sending reputation).",
                "error",
            )
            return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))

    subject = request.form.get("subject", "").strip()
    body = request.form.get("body", "").strip()
    resume_row = storage.get_resume()
    attachment_path = resume_row["resume_pdf_path"] if resume_row else None

    try:
        message_id = gmail_client.send_message(recruiter["email"], subject, body, attachment_path)
    except Exception as exc:
        flash(f"Send failed: {exc}", "error")
        return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))

    storage.mark_draft_sent(draft_id, subject, body, message_id)
    if config.TEST_SEND_MODE:
        flash(f"Sent in TEST MODE (redirected to {config.TEST_SEND_EMAIL}).", "success")
    else:
        flash("Sent.", "success")
    return redirect(url_for("company_recruiters", company_id=recruiter["company_id"]))


if __name__ == "__main__":
    # Port 5000 collides with macOS's AirPlay Receiver on the loopback interface.
    app.run(debug=True, port=5001)
