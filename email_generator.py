import json

from openai import OpenAI

import config

client = OpenAI(api_key=config.OPENAI_API_KEY)

SUMMARIZE_SYSTEM_PROMPT = """\
Summarize the given resume into a concise paragraph covering: education (school, degree, \
graduation timeline), and the most notable experience/projects and skills. Prioritize \
specific, concrete, interesting details over generic descriptions -- name actual projects, \
technologies, and outcomes (e.g. "built a real-time pricing API handling 10k req/s using Go \
and Redis" rather than "developed APIs and worked with various technologies"). Pay particular \
attention to preserving specific named AI/ML frameworks, protocols, and paradigms if present \
(e.g. LangChain, RAG, MCP/Model Context Protocol, agentic AI, specific model providers) -- \
don't flatten these into a generic phrase like "AI operations platform." If the resume itself \
is vague on a point, keep the summary vague there too rather than inventing detail. This \
summary will be used as context for drafting outreach emails, not shown directly to anyone. \
Do not editorialize or add anything not present in the resume."""

COMPANY_INTEREST_SYSTEM_PROMPT = """\
You write a single short sentence for a cold outreach email from a job-seeker to a company \
recruiter, expressing genuine-sounding interest in that specific company. If verified research \
notes about the company are provided, your sentence MUST reference at least one concrete, \
checkable detail from them -- a specific number (revenue, users, headcount), a named \
product/initiative, or a dated event -- not just a paraphrase of a general theme like "focus on \
innovation" or "commitment to AI." If no research notes are provided, you may draw on general, \
well-known knowledge about the company (its industry, what it's broadly known for) instead, but \
do not invent specific, checkable claims -- no fake recent news, product launches, financial \
figures, or internal initiatives you're not confident are real. Avoid generic-sounding openers \
regardless of source ("committed to...", "passionate about...", "excited about your innovative \
use of...", "I've always admired...") -- it should read as a specific, reasoned observation \
grounded in a real detail, not a compliment. One sentence only, no greeting, no sign-off. \
Return JSON: {"sentence": "..."}"""


def summarize_resume(raw_text):
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": raw_text},
        ],
    )
    content = resp.choices[0].message.content
    if content is None:
        raise ValueError("Response content is None")
    return content.strip()


def company_interest_sentence(resume_summary, company_name, company_research=None):
    research_block = f"Verified research notes about the company:\n{company_research}\n\n" if company_research else ""
    user_prompt = (
        f"Company: {company_name}\n"
        f"{research_block}"
        f"Candidate background: {resume_summary}\n\n"
        f"Write the one-sentence company-interest line for this candidate reaching out to {company_name}."
    )
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": COMPANY_INTEREST_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    content = resp.choices[0].message.content
    if content is None:
        raise ValueError("Response content is None")
    return json.loads(content)["sentence"].strip()
