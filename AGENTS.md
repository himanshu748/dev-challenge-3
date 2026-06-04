# HireIQ Notes

## Project Shape
- FastAPI app with a vanilla HTML/CSS/JS frontend.
- Runtime state is local JSON at `data/runtime_state.json`; keep it ignored.
- Hugging Face generates recruiting content and Notion stores workspace/job/candidate/offer records.

## Commands
- Run tests with `python -m pytest`.
- Check syntax with `python -m compileall app tests`.
- Start locally with `uvicorn app.main:app --reload`.

## Conventions
- The app must import and serve health/static routes without API tokens.
- Provider-backed routes should fail with explicit config errors when `HF_API_KEY`, `NOTION_TOKEN`, or `NOTION_PARENT_PAGE_ID` are missing.
- `HF_TOKEN` may be used as a local fallback alias for `HF_API_KEY`; never commit real provider tokens.
- Notion REST fallback errors should stay sanitized and raise `HireIQError` instead of returning API error dicts as app data.
- Keep MCP imports lazy/optional so the REST fallback and local tests work without the MCP package installed.
- Do not commit `.env`, `data/runtime_state.json`, `.playwright-mcp/`, caches, logs, or generated reports.
