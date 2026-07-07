# HireIQ

HireIQ is a FastAPI recruiting assistant that uses a HuggingFace model to create polished job descriptions, screen candidates against stored job requirements, and generate offer letters. All pipeline state (jobs, candidates, offers, logs) is stored locally in a JSON runtime store.

## Stack

- Python
- FastAPI
- huggingface_hub AsyncInferenceClient
- Vanilla HTML/CSS/JS frontend

## Environment

Create a `.env` file with:

```bash
HF_API_KEY=
```

`HF_API_KEY` is the deployment variable; local runs may use `HF_TOKEN` as a fallback alias if it is already loaded in the process environment.
Optional: set `HF_MODEL` to override the default model (`Qwen/Qwen3-235B-A22B-Instruct-2507`).
Optional: set `CORS_ORIGINS` to a comma-separated list of browser origins allowed to call the API. It defaults to local Uvicorn origins.

The app can import and serve health/static routes without secrets. `/api/setup` works without any tokens (it only initializes the local store). AI-backed routes (`add-job`, `screen-candidate`, `generate-offer`) return explicit configuration errors until `HF_API_KEY` is set.

## Install and run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

### Docker

```bash
docker build -t hireiq .
docker run --env-file .env -p 8000:8000 hireiq
```

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
- `GET /api/jobs`
- `GET /api/candidates`
- `GET /api/logs`
- `GET /api/health`

Every write endpoint returns:

- `summary`
- `details`
- `log_output`
- `pipeline_counts`

## Notes

- The HuggingFace request uses model `Qwen/Qwen3-235B-A22B-Instruct-2507` by default (configurable via `HF_MODEL` env var) through the async inference client, so generation never blocks the event loop.
- Model responses that fail JSON parsing are retried once with a corrective prompt before returning an error.
- All state lives in `data/runtime_state.json`; delete the file to reset the pipeline.
- Keep `.env`, `data/runtime_state.json`, caches, and generated output out of git.
