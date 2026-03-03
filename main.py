import os
import json

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(
    title="AI SDR Lead Extraction API",
    description="Extract structured B2B lead intelligence from any company website.",
)

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


class ExtractRequest(BaseModel):
    target_url: str
    seller_context: str | None = None
    model: str = "gpt-4o-mini"

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "target_url": "https://acmehotels.com",
                    "seller_context": (
                        "We provide cloud-based HR software for mid-size companies."
                    ),
                    "model": "gpt-4o-mini",
                }
            ]
        }
    }


@app.post("/extract-leads")
async def extract_leads(request: ExtractRequest):
    # Step 1: Fetch clean Markdown content via Jina Reader
    jina_url = f"https://r.jina.ai/{request.target_url}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(jina_url)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Failed to fetch content from target URL: {e.response.status_code}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=502,
                detail=f"Network error while fetching target URL: {str(e)}",
            )

    markdown_content = response.text

    if not markdown_content.strip():
        raise HTTPException(
            status_code=422,
            detail="No content could be extracted from the provided URL.",
        )

    # Step 2: Build dynamic system prompt from seller context
    seller_context = request.seller_context or DEFAULT_SELLER_CONTEXT
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(seller_context=seller_context)

    # Step 3: Pass Markdown to LLM and extract structured lead data
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="OPENAI_API_KEY is not configured on the server.",
        )

    openai_client = OpenAI(api_key=api_key)

    try:
        completion = openai_client.chat.completions.create(
            model=request.model,
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
    except Exception as e:
        raise HTTPException(
            status_code=502,
            detail=f"LLM API error: {str(e)}",
        )

    raw_json = completion.choices[0].message.content

    try:
        lead_data = json.loads(raw_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="LLM returned an invalid JSON response.",
        )

    return lead_data
