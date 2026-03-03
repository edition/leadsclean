from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from core import extract_lead_intelligence

app = FastAPI(
    title="AI SDR Lead Extraction API",
    description="Extract structured B2B lead intelligence from any company website.",
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
    try:
        return await extract_lead_intelligence(
            url=request.target_url,
            seller_context=request.seller_context,
            model=request.model,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except EnvironmentError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
