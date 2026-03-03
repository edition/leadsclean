"""
LeadsClean MCP Server — B2B Sales Intelligence for AI Agents

Exposes structured lead extraction as MCP tools callable by any MCP-compatible
AI agent (Claude Desktop, Cursor, custom LangChain/CrewAI agents, etc.).

Transport modes:
  stdio (default)       — for local agent clients (Claude Desktop, Cursor)
  streamable-http       — for remote/production agent pipelines

Usage:
  python mcp_server.py                        # stdio
  python mcp_server.py --transport http       # Streamable HTTP on port 8001
"""

import argparse
import asyncio
import json

from mcp.server.fastmcp import FastMCP

from core import extract_lead_intelligence as _extract_lead_intelligence

mcp = FastMCP(
    name="leadsclean",
    instructions=(
        "LeadsClean gives AI agents structured B2B lead intelligence extracted "
        "directly from company websites. Use `extract_lead_intelligence` for a single "
        "target, or `batch_extract_leads` when processing a list of URLs in parallel. "
        "Always supply a `seller_context` describing what you sell so the analysis is "
        "relevant to your outreach — otherwise a generic default is used."
    ),
)


@mcp.tool()
async def extract_lead_intelligence(
    url: str,
    seller_context: str | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Extract structured B2B lead intelligence from a single company website.

    Fetches the page via Jina Reader, then uses an LLM to return a JSON object with:
    - company_name
    - core_business_summary  (≤15 words)
    - product_category_match (does this prospect need what the seller offers?)
    - recent_company_trigger (funding, hiring surge, expansion, news — buying signal)
    - inferred_business_need (specific need that aligns with seller offering)
    - icebreaker_hook_business (personalized opening line referencing core business)
    - icebreaker_hook_news    (opening line referencing a recent trigger, if found)
    - data_provenance         (GDPR metadata: source type, PII flag, legal basis)

    Args:
        url: Full URL of the target company website (e.g. "https://acmecorp.com").
        seller_context: One-sentence description of what the seller offers and to whom.
                        Omit to use the server default. Example:
                        "We provide cloud HR software to mid-size logistics companies."
        model: Model ID — provider is inferred from the name prefix:
               gpt-*/o1-*/o3-* → OpenAI (OPENAI_API_KEY, default: gpt-4o-mini),
               claude-*        → Anthropic (ANTHROPIC_API_KEY),
               qwen-*          → Alibaba DashScope (DASHSCOPE_API_KEY),
               abab*/minimax-* → MiniMax (MINIMAX_API_KEY).

    Returns:
        JSON string containing the structured lead intelligence object.
    """
    try:
        result = await _extract_lead_intelligence(
            url=url,
            seller_context=seller_context,
            model=model,
        )
        return json.dumps(result, ensure_ascii=False, indent=2)
    except ValueError as e:
        return json.dumps({"error": str(e), "url": url})
    except EnvironmentError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": f"Extraction failed: {str(e)}", "url": url})


@mcp.tool()
async def batch_extract_leads(
    urls: list[str],
    seller_context: str | None = None,
    model: str = "gpt-4o-mini",
) -> str:
    """
    Extract B2B lead intelligence from multiple company websites in parallel.

    Runs all extractions concurrently — optimised for agent pipelines processing
    prospect lists. Each URL is processed independently; failures are captured per
    record without aborting the batch.

    Args:
        urls: List of company website URLs to analyse (max 20 per call).
              Example: ["https://acmecorp.com", "https://betahotels.io"]
        seller_context: One-sentence description of what the seller offers and to whom.
                        Applied uniformly across all URLs in the batch.
        model: Model ID — same provider-prefix rules as extract_lead_intelligence.
               Applied uniformly to all URLs in the batch.

    Returns:
        JSON string containing a list of results in the same order as `urls`.
        Each entry is either the lead intelligence object (including data_provenance)
        or an error object with keys {"error": "...", "url": "..."}.
    """
    if len(urls) > 20:
        return json.dumps(
            {"error": "Batch size exceeds limit of 20 URLs per call.", "received": len(urls)}
        )

    async def _extract_one(url: str) -> dict:
        try:
            return await _extract_lead_intelligence(
                url=url,
                seller_context=seller_context,
                model=model,
            )
        except Exception as e:
            return {"error": str(e), "url": url}

    results = await asyncio.gather(*[_extract_one(u) for u in urls])
    return json.dumps(list(results), ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description="LeadsClean MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode: 'stdio' for local clients, 'http' for remote agents (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for HTTP transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
