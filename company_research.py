from ddgs import DDGS
from langchain.agents import create_agent
from langchain_core.tools import tool

import config

SYSTEM_PROMPT = """\
You research companies for a job-seeker writing cold outreach emails to recruiters. You'll be \
given the company name and a summary of the candidate's background. Search at least three \
times: once for a general overview (what the company does, its industry, its focus), once with \
a recency filter for recent news specifically (product launches, notable initiatives, recent \
engineering work, recent financial results), and once targeted at the intersection of the \
company and the candidate's specific skills/domain (e.g. if the candidate has AI/ML, data, or \
software engineering experience, search for how this company actually uses that kind of \
technology in its business). Then write a short factual briefing (2-4 sentences) a candidate \
could reference in an outreach email, prioritizing the most specific and recent verifiable \
facts you found, especially any that connect to the candidate's background -- but don't force a \
connection your searches didn't actually support. Stick to what the search results actually \
support -- if you can't find anything specific and recent, say so plainly instead of guessing."""


@tool
def web_search(query: str, recency: str = "") -> str:
    """Search the web and return the top result titles, URLs, and snippets.

    Args:
        query: The search query.
        recency: Optional filter to bias results toward recent content. One of "d" (past day),
            "w" (past week), "m" (past month), "y" (past year), or "" (no filter, default) for
            general/background searches.
    """
    results = DDGS().text(query, max_results=8, timelimit=recency or None)
    if not results:
        return "No results found."
    return "\n\n".join(f"{r['title']}\n{r['href']}\n{r['body']}" for r in results)


def research_company(company_name, resume_summary):
    """Runs a LangChain agent that web-searches the company -- including for ties to the
    candidate's specific background -- and returns a short factual briefing."""
    agent = create_agent(
        model=f"openai:{config.OPENAI_MODEL}",
        tools=[web_search],
        system_prompt=SYSTEM_PROMPT,
    )
    user_message = f"Research this company: {company_name}\n\nCandidate background: {resume_summary}"
    result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    return result["messages"][-1].content.strip()
