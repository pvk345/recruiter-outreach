import requests

import config

BASE_URL = "https://api.apollo.io/api/v1"


def _post(path, payload):
    resp = requests.post(
        f"{BASE_URL}/{path}",
        headers={
            "x-api-key": config.APOLLO_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        json=payload,
        timeout=15,
    )
    if not resp.ok:
        raise RuntimeError(f"Apollo API error {resp.status_code} on {path}: {resp.text}")
    return resp.json()


def search_organizations(company_name, per_page=5):
    """Resolve a company name to candidate Apollo organizations. Costs credits per page."""
    data = _post("mixed_companies/search", {"q_organization_name": company_name, "per_page": per_page})
    return [
        {
            "apollo_org_id": org["id"],
            "name": org["name"],
            "domain": org.get("primary_domain"),
            "website_url": org.get("website_url"),
            "linkedin_url": org.get("linkedin_url"),
        }
        for org in data.get("organizations", [])
    ]


def search_people(org_id, per_page=25):
    """List recruiting-titled people at an org, restricted to configured locations. Free
    preview: title only, no name/email yet."""
    data = _post(
        "mixed_people/api_search",
        {
            "organization_ids": [org_id],
            "person_titles": config.RECRUITER_TITLES,
            "person_locations": config.RECRUITER_LOCATIONS,
            "per_page": per_page,
        },
    )
    return [{"id": person["id"], "title": person.get("title") or ""} for person in data.get("people", [])]


def enrich_person(person_id):
    """Unlock full name, LinkedIn, and email for one person. Costs 1 credit."""
    data = _post("people/match", {"id": person_id, "reveal_personal_emails": True})
    person = data.get("person")
    if not person or not person.get("email"):
        return None
    return {
        "id": person["id"],
        "name": person.get("name"),
        "title": person.get("title"),
        "linkedin_url": person.get("linkedin_url"),
        "email": person.get("email"),
    }


def is_university_recruiter(title):
    title_lower = (title or "").lower()
    return any(keyword in title_lower for keyword in config.UNIVERSITY_RECRUITER_KEYWORDS)


def is_technical_recruiter(title):
    title_lower = (title or "").lower()
    return any(keyword in title_lower for keyword in config.TECHNICAL_RECRUITER_KEYWORDS)
