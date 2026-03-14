# HireIQ

HireIQ is a FastAPI recruiting assistant that uses Claude Sonnet 4 with the Notion MCP server attached to stand up a recruiting workspace, create polished job descriptions, screen candidates, and generate offer letters.

## Stack

- Python
- FastAPI
- httpx
- Vanilla HTML/CSS/JS frontend

## Environment

Create a `.env` file with:

```bash
ANTHROPIC_API_KEY=...
NOTION_TOKEN=...
NOTION_PARENT_PAGE_ID=...
```

Important: `NOTION_TOKEN` must be a current access token for the remote Notion MCP server at `https://mcp.notion.com/sse`. A plain Notion internal integration token is not enough for that remote MCP connection.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

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

- The Anthropic request uses model `claude-sonnet-4-20250514`.
- The app attaches Notion MCP via `https://mcp.notion.com/sse`.
- The request includes beta header `mcp-client-2025-04-04` as requested.
- Pipeline counts are tracked locally and surfaced in the UI from the backend log stream.
