# LeadsClean MCP Server

**Category: Sales Intelligence · B2B Lead Extraction**

An MCP (Model Context Protocol) server that gives AI agents structured B2B lead intelligence extracted directly from company websites. Point it at any URL and get back a clean JSON object — company summary, buying signals, inferred needs, and personalised icebreaker lines — ready to drop into your outreach pipeline.

Built for agent pipelines. Works with Claude Desktop, Cursor, and any MCP-compatible client.

<a href="https://glama.ai/mcp/servers/@edition/leads-clean-mcp-server">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@edition/leads-clean-mcp-server/badge" alt="LeadsClean Server MCP server" />
</a>

---

## Tools

| Tool | Description |
|------|-------------|
| `extract_lead_intelligence` | Analyse a single company URL and return structured lead intel |
| `batch_extract_leads` | Analyse up to 20 URLs in parallel — designed for agent list-processing |

### Output schema

```json
{
  "company_name": "Acme Hotels Group",
  "core_business_summary": "Boutique hotel chain with 12 properties across Europe.",
  "product_category_match": "Strong match — hotel groups purchase furniture in bulk for room refits.",
  "recent_company_trigger": "Announced expansion to 3 new cities in Q1 2026, adding 400+ rooms.",
  "inferred_business_need": "Bulk furnishing for new hotel rooms on tight fit-out timelines.",
  "icebreaker_hook_business": "Running 12 properties across Europe is impressive — furnishing them at scale is where we help.",
  "icebreaker_hook_news": "Saw the Q1 expansion news — we help hotel groups source wholesale beds and sofas fast.",
  "data_provenance": {
    "source_url": "https://acmehotels.com",
    "source_type": "public_website",
    "collection_method": "jina_reader_public_fetch",
    "contains_pii": false,
    "gdpr_basis": "legitimate_interest",
    "gdpr_notes": "Extracted solely from publicly available company web pages. No personal data collected. Compliant with GDPR Art. 6(1)(f)."
  }
}
```

Every response includes `data_provenance` — a machine-readable GDPR metadata block indicating data source, PII status, and legal basis. This lets enterprise security teams approve the integration without a manual compliance review.

---

## Quick start

### Prerequisites

- Python 3.11+
- An API key for at least one supported LLM provider (see [Environment variables](#environment-variables) below)

### Install

```bash
pip install mcp-leadsclean
```

Or clone and install from source:

```bash
git clone https://github.com/edition/leadsclean
cd leadsclean
pip install -e .
```

---

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "leadsclean": {
      "command": "mcp-leadsclean",
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

Set the key for whichever provider(s) you use (see [Environment variables](#environment-variables)).

### Cursor

Add to your Cursor MCP config (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "leadsclean": {
      "command": "mcp-leadsclean",
      "env": {
        "OPENAI_API_KEY": "sk-..."
      }
    }
  }
}
```

### HTTP transport (production agent pipelines)

For remote agents or multi-tenant deployments, run with Streamable HTTP transport:

```bash
OPENAI_API_KEY=sk-... mcp-leadsclean --transport http --port 8001
```

The server exposes a single MCP endpoint at `http://localhost:8001/mcp`.

---

## Demo mode

Try the server without an API key — useful for testing your agent pipeline or reviewing the output schema:

```bash
LEADSCLEAN_DEMO=1 mcp-leadsclean
```

All tool calls return a sanitised fixture response when `LEADSCLEAN_DEMO=1` is set. The response includes `"_demo": true` so agents can detect and discard it.

---

## Environment variables

The `model` parameter controls which provider is used. Provider is inferred from the model-name prefix — set the corresponding key:

| Variable | Required when | Model prefix | Description |
|----------|--------------|--------------|-------------|
| `OPENAI_API_KEY` | Using OpenAI (default) | `gpt-*`, `o1-*`, `o3-*` | OpenAI API key |
| `ANTHROPIC_API_KEY` | Using Claude | `claude-*` | Anthropic API key |
| `DASHSCOPE_API_KEY` | Using Alibaba Qwen | `qwen-*` | Alibaba DashScope API key |
| `MINIMAX_API_KEY` | Using MiniMax | `abab*`, `minimax-*` | MiniMax API key |
| `LEADSCLEAN_DEMO` | — | — | Set to `1` to return fixture data without any LLM call |

The default model is `gpt-4o-mini` (OpenAI). To switch provider, pass the desired model ID in the tool call — e.g. `claude-3-5-haiku-20241022` for Anthropic, `qwen-turbo` for Alibaba.

---

## REST API

A standard FastAPI REST endpoint is also available for non-MCP integrations:

```bash
uvicorn main:app --reload
```

```bash
curl -X POST http://localhost:8000/extract-leads \
  -H "Content-Type: application/json" \
  -d '{
    "target_url": "https://acmecorp.com",
    "seller_context": "We provide cloud HR software to mid-size logistics companies."
  }'
```

---

## Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server (stdio)
python mcp_server.py

# Run MCP server (HTTP, port 8001)
python mcp_server.py --transport http

# Run REST API
uvicorn main:app --reload
```

---

## How it works

1. **Fetch** — retrieves clean Markdown from the target URL via [Jina Reader](https://jina.ai/reader/)
2. **Extract** — passes the content to your chosen LLM (OpenAI, Anthropic Claude, Alibaba Qwen, or MiniMax) with a structured prompt
3. **Return** — outputs a JSON object matching the schema above

Content never leaves the pipeline: no data is stored by LeadsClean.

---

## Built with Claude

This project was developed with the assistance of [Claude](https://claude.ai) by Anthropic — an AI assistant used for code generation, architecture design, and documentation.

---

## License

MIT