import json
import os

import httpx
from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# Demo fixture — returned when LEADSCLEAN_DEMO=1 is set.
# Lets reviewers and new users see the output schema without an API key.
# ---------------------------------------------------------------------------
_DEMO_FIXTURE = {
    "_demo": True,
    "company_name": "Acme Hotels Group",
    "core_business_summary": "Boutique hotel chain with 12 properties across Europe.",
    "product_category_match": (
        "Strong match — hotel groups purchase furniture in bulk for room refits and new openings."
    ),
    "recent_company_trigger": (
        "Announced expansion to 3 new cities in Q1 2026, adding 400+ rooms across the portfolio."
    ),
    "inferred_business_need": (
        "Bulk furnishing (beds, sofas) for new hotel rooms on tight fit-out timelines."
    ),
    "icebreaker_hook_business": (
        "Running 12 properties across Europe is impressive — furnishing them at scale is exactly where we help."
    ),
    "icebreaker_hook_news": (
        "Saw the Q1 expansion news — we help hotel groups source wholesale beds and sofas fast when timelines are tight."
    ),
    "data_provenance": {
        "source_url": "https://acmehotels.com",
        "source_type": "public_website",
        "collection_method": "jina_reader_public_fetch",
        "contains_pii": False,
        "gdpr_basis": "legitimate_interest",
        "gdpr_notes": (
            "Extracted solely from publicly available company web pages. "
            "No personal data collected. Compliant with GDPR Art. 6(1)(f)."
        ),
    },
}

SYSTEM_PROMPT_TEMPLATE = """
You are an elite B2B Sales Intelligence Agent. Your primary function is to analyze raw, unstructured text scraped from target company websites and extract highly accurate, structured commercial signals.
STRICT FACTUALITY: You must extract information strictly based on the provided text. DO NOT hallucinate. If a specific piece of information cannot be found, you MUST output null for that field.
Seller context: {seller_context}
You MUST respond ONLY with a valid JSON object matching this exact schema:
{{
  "company_name": "String",
  "core_business_summary": "String (Max 15 words)",
  "product_category_match": "String or null — does this company likely need what the seller offers? Explain briefly.",
  "recent_company_trigger": "String or null — any recent news, expansion, hiring surge, or event that signals a buying opportunity.",
  "inferred_business_need": "String or null — based on their business model, what specific need aligns with the seller's offering?",
  "icebreaker_hook_business": "String — a concise, personalized opening line referencing their core business.",
  "icebreaker_hook_news": "String or null — a concise opening line referencing a recent trigger or news, if found."
}}
"""

DEFAULT_SELLER_CONTEXT = (
    "We supply wholesale furniture (sofas and beds, spot inventory) "
    "to B2B buyers such as hotels, retailers, and interior design firms."
)

_GDPR_NOTES = (
    "Extracted solely from publicly available company web pages. "
    "No personal data collected. Compliant with GDPR Art. 6(1)(f)."
)


def _build_provenance(url: str) -> dict:
    return {
        "source_url": url,
        "source_type": "public_website",
        "collection_method": "jina_reader_public_fetch",
        "contains_pii": False,
        "gdpr_basis": "legitimate_interest",
        "gdpr_notes": _GDPR_NOTES,
    }


async def fetch_page_content(url: str) -> str:
    """Fetch clean Markdown content for a URL via Jina Reader."""
    jina_url = f"https://r.jina.ai/{url}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(jina_url)
        response.raise_for_status()
    content = response.text
    if not content.strip():
        raise ValueError("No content could be extracted from the provided URL.")
    return content


async def extract_lead_intelligence(
    url: str,
    seller_context: str | None = None,
    model: str = "gpt-4o-mini",
) -> dict:
    """
    Fetch a company website and return structured B2B lead intelligence.

    Returns a dict with keys:
    - company_name
    - core_business_summary
    - product_category_match
    - recent_company_trigger
    - inferred_business_need
    - icebreaker_hook_business
    - icebreaker_hook_news
    - data_provenance  (GDPR / source metadata)
    """
    if os.getenv("LEADSCLEAN_DEMO"):
        return _DEMO_FIXTURE

    markdown_content = await fetch_page_content(url)

    resolved_seller_context = seller_context or DEFAULT_SELLER_CONTEXT
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(seller_context=resolved_seller_context)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not configured.")

    client = AsyncOpenAI(api_key=api_key)
    completion = await client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    "Analyze the following website content and extract lead intelligence:\n\n"
                    + markdown_content
                ),
            },
        ],
    )

    result = json.loads(completion.choices[0].message.content)
    result["data_provenance"] = _build_provenance(url)
    return result
