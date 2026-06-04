# HireIQ

HireIQ is a FastAPI recruiting assistant that uses a HuggingFace model with the Notion MCP server attached to stand up a recruiting workspace, create polished job descriptions, screen candidates, and generate offer letters.

## Stack

- Python
- FastAPI
- huggingface_hub MCPClient
- Vanilla HTML/CSS/JS frontend

## Environment

Create a `.env` file with:

```bash
HF_API_KEY=
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
```

`HF_API_KEY` is the deployment variable; local runs may use `HF_TOKEN` as a fallback alias if it is already loaded in the process environment.
Optional: set `HF_MODEL` to override the default model (`Qwen/Qwen2.5-72B-Instruct`).
Optional: set `CORS_ORIGINS` to a comma-separated list of browser origins allowed to call the API. It defaults to local Uvicorn origins.

Important: `NOTION_TOKEN` must be a current access token for the remote Notion MCP server at `https://mcp.notion.com/sse`. A plain Notion internal integration token is not enough for that remote MCP connection.

The app can import and serve health/static routes without secrets. Provider-backed write routes return explicit configuration errors until the required keys are set. `/api/health` reports `notion_transport` so MCP stdio and REST fallback are not confused.

If `NOTION_TOKEN` is not loaded, live Notion setup/job/screening/offer routes cannot be tested. The REST fallback raises sanitized errors for unsupported tools, missing Notion arguments, non-2xx Notion responses, or invalid Notion JSON.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Verify

```bash
python -m pytest
python -m compileall app tests
```

## API

- `POST /api/setup`
- `POST /api/add-job`
- `POST /api/screen-candidate`
- `POST /api/generate-offer`
- `GET /api/logs`
- `GET /api/health`

Every write endpoint returns:

- `summary`
- `notion_urls`
- `details`
- `log_output`
- `pipeline_counts`

## Notes

- The HuggingFace request uses model `Qwen/Qwen2.5-72B-Instruct` by default (configurable via `HF_MODEL` env var).
- The app prefers the Notion MCP package when available and falls back to direct Notion REST calls for supported operations.
- Pipeline counts are tracked locally and surfaced in the UI from the backend log stream.
- Keep `.env`, `.playwright-mcp/`, `data/runtime_state.json`, caches, and generated output out of git.
