# HireIQ Notes

## Project Shape
- FastAPI app with a vanilla HTML/CSS/JS frontend.
- Runtime state is local JSON at `data/runtime_state.json`; keep it ignored.
- Hugging Face generates recruiting content; jobs, candidates, offers, and logs persist in the local runtime store.

## Commands
- Run tests with `python -m pytest`.
- Check syntax with `python -m compileall app tests`.
- Start locally with `uvicorn app.main:app --reload`.

## Conventions
- The app must import and serve health/static routes without API tokens.
- `/api/setup` must work without tokens; AI-backed routes should fail with explicit config errors when `HF_API_KEY` is missing.
- `HF_TOKEN` may be used as a local fallback alias for `HF_API_KEY`; never commit real provider tokens.
- Model-output parse failures raise sanitized `HireIQError`s and are retried once before surfacing.
- Do not commit `.env`, `data/runtime_state.json`, caches, logs, or generated reports.
