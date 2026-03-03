import time

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from auth import read_api_key, require_api_key
from core import extract_lead_intelligence
from db import init_db, log_usage

# ---------------------------------------------------------------------------
# Response models — also drive the OpenAPI schema shown in /docs
# ---------------------------------------------------------------------------

class DataProvenance(BaseModel):
    source_url: str = Field(description="The URL that was fetched and analysed.")
    source_type: str = Field(
        description="Always 'public_website' — only publicly accessible pages are fetched."
    )
    collection_method: str = Field(
        description="Fetch mechanism: Jina Reader public API converts the page to clean Markdown."
    )
    contains_pii: bool = Field(
        description=(
            "Whether the extracted data contains personal identifiable information. "
            "Always false — only company-level signals are extracted, never individual contact data."
        )
    )
    gdpr_basis: str = Field(
        description="GDPR legal basis for processing. 'legitimate_interest' per Art. 6(1)(f)."
    )
    gdpr_notes: str = Field(description="Plain-language GDPR compliance statement.")


class LeadIntelligenceResponse(BaseModel):
    # extra="allow" lets the _demo flag pass through in demo-mode responses
    model_config = ConfigDict(extra="allow")

    company_name: str = Field(description="Name of the target company as found on their website.")
    core_business_summary: str = Field(
        description="One-line business description, max 15 words."
    )
    product_category_match: str | None = Field(
        description=(
            "Whether this company is likely to need the seller's product. "
            "Null if the match is unclear from the page content."
        )
    )
    recent_company_trigger: str | None = Field(
        description=(
            "Recent buying signal: funding round, expansion, hiring surge, product launch, or news. "
            "Null if no trigger found."
        )
    )
    inferred_business_need: str | None = Field(
        description=(
            "Specific operational need that aligns with the seller's offering, "
            "inferred from their business model. Null if not determinable."
        )
    )
    icebreaker_hook_business: str = Field(
        description="Personalised cold-outreach opening line referencing the company's core business."
    )
    icebreaker_hook_news: str | None = Field(
        description=(
            "Personalised opening line referencing a recent trigger or news item. "
            "Null if no trigger was found."
        )
    )
    data_provenance: DataProvenance = Field(
        description="Data-source and GDPR metadata. Included on every response for compliance audits."
    )


class UsageResponse(BaseModel):
    plan: str = Field(description="Current subscription plan.")
    calls_used: int = Field(description="API calls consumed this calendar month.")
    monthly_limit: int = Field(description="Maximum calls allowed per month on this plan.")
    calls_remaining: int = Field(description="Calls remaining before the monthly limit is hit.")
    reset_at: str = Field(description="ISO date (YYYY-MM-DD) when calls_used resets to zero.")


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    target_url: str = Field(description="Full URL of the target company website.")
    seller_context: str | None = Field(
        default=None,
        description=(
            "One-sentence description of what the seller offers and to whom. "
            "Drives the relevance analysis and icebreaker generation. "
            "Omit to use the server default (wholesale furniture)."
        ),
    )
    model: str = Field(
        default="gpt-4o-mini",
        description=(
            "Model ID — the LLM provider is inferred from the model name prefix. "
            "OpenAI (OPENAI_API_KEY): 'gpt-4o-mini' (default), 'gpt-4o', 'o3-mini'. "
            "Anthropic (ANTHROPIC_API_KEY): 'claude-haiku-4-5-20251001', 'claude-sonnet-4-6'. "
            "Alibaba Qwen (DASHSCOPE_API_KEY): 'qwen-turbo', 'qwen-plus', 'qwen-max'. "
            "MiniMax (MINIMAX_API_KEY): 'abab6.5s-chat', 'abab6.5-chat'."
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "target_url": "https://acmehotels.com",
                    "seller_context": (
                        "We supply wholesale furniture (sofas and beds) "
                        "to hotels, retailers, and interior design firms."
                    ),
                    "model": "gpt-4o-mini",
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="LeadsClean — B2B Lead Intelligence API",
    description=(
        "Extract structured B2B sales intelligence from any company website.\n\n"
        "**Authentication:** All endpoints require an `X-API-Key` header. "
        "Contact us to obtain a key.\n\n"
        "**Category:** Sales Intelligence\n\n"
        "LeadsClean fetches a target company's public website via Jina Reader, "
        "then uses an LLM to extract buying signals, inferred needs, and personalised "
        "icebreaker lines — ready to drop into your outreach pipeline.\n\n"
        "Every response includes a `data_provenance` block with GDPR metadata "
        "(source type, PII flag, legal basis) to support enterprise security reviews."
    ),
    version="0.2.0",
    openapi_tags=[
        {
            "name": "Lead Extraction",
            "description": "Analyse company websites and return structured lead intelligence.",
        },
        {
            "name": "Account",
            "description": "API key usage and quota information.",
        },
    ],
    contact={"name": "LeadsClean", "url": "https://github.com/your-org/leadsclean"},
    license_info={"name": "MIT"},
)


@app.on_event("startup")
async def startup() -> None:
    init_db()


# ---------------------------------------------------------------------------
# POST /extract-leads
# ---------------------------------------------------------------------------

@app.post(
    "/extract-leads",
    response_model=LeadIntelligenceResponse,
    summary="Extract lead intelligence from a company URL",
    description=(
        "Fetches the target company's public website, extracts clean Markdown via Jina Reader, "
        "and uses an LLM to return structured B2B sales intelligence.\n\n"
        "The response includes buying signals, an inferred business need relative to the "
        "seller's offering, two personalised icebreaker lines, and a `data_provenance` block "
        "for GDPR compliance.\n\n"
        "**Rate-limit headers** are included on every response:\n"
        "- `X-RateLimit-Limit` — monthly call quota\n"
        "- `X-RateLimit-Remaining` — calls left this month\n"
        "- `X-RateLimit-Reset` — date the quota resets (YYYY-MM-DD)"
    ),
    tags=["Lead Extraction"],
    responses={
        200: {"description": "Structured lead intelligence extracted from the target URL."},
        401: {"description": "Missing or invalid API key."},
        422: {"description": "Invalid input or no content could be extracted from the URL."},
        429: {"description": "Monthly call limit reached."},
        500: {"description": "Server configuration error (e.g. missing OPENAI_API_KEY)."},
        502: {"description": "Upstream error from Jina Reader or the LLM provider."},
    },
)
async def extract_leads(
    request: ExtractRequest,
    response: Response,
    background_tasks: BackgroundTasks,
    key_info: dict = Depends(require_api_key),
) -> LeadIntelligenceResponse:
    t0 = time.monotonic()
    status = "ok"
    try:
        result = await extract_lead_intelligence(
            url=request.target_url,
            seller_context=request.seller_context,
            model=request.model,
        )
        response.headers["X-RateLimit-Limit"] = str(key_info["monthly_limit"])
        response.headers["X-RateLimit-Remaining"] = str(
            key_info["monthly_limit"] - key_info["calls_used"]
        )
        response.headers["X-RateLimit-Reset"] = key_info["reset_at"]
        return result
    except ValueError as e:
        status = "error"
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        status = "error"
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        status = "error"
        raise HTTPException(status_code=502, detail=str(e))
    finally:
        latency_ms = int((time.monotonic() - t0) * 1000)
        background_tasks.add_task(
            log_usage,
            key_info["key"],
            request.target_url,
            request.model,
            latency_ms,
            status,
        )


# ---------------------------------------------------------------------------
# GET /usage
# ---------------------------------------------------------------------------

@app.get(
    "/usage",
    response_model=UsageResponse,
    summary="Get current API key usage",
    description="Returns quota usage for the authenticated API key. Does not count as a billable call.",
    tags=["Account"],
    responses={
        200: {"description": "Current usage and quota for this API key."},
        401: {"description": "Missing or invalid API key."},
    },
)
async def get_usage(key_info: dict = Depends(read_api_key)) -> UsageResponse:
    return UsageResponse(
        plan=key_info["plan"],
        calls_used=key_info["calls_used"],
        monthly_limit=key_info["monthly_limit"],
        calls_remaining=key_info["monthly_limit"] - key_info["calls_used"],
        reset_at=key_info["reset_at"],
    )
