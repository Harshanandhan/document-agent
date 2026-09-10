# Document Processing Agent

Lab FastAPI + Claude **tool-use** agent for document workflows (PDF/CSV/Excel/images).
Upload files + a task; the agent can call local tools (read, split PDF, validate invoice fields, export, copy, mock/real email).

This is a **portfolio lab**, not a production multi-tenant product.

## Live demo

- **URL:** https://luminous-compassion-production-1f80.up.railway.app
- **Health:** https://luminous-compassion-production-1f80.up.railway.app/health
- **Honesty:** UI reads `/health`. If `ANTHROPIC_API_KEY` is set in Railway, live agent runs are enabled. If missing, the public page stays up as a status + sample-flow demo and `POST /process` returns 503 (no fake AI).

## What the code actually does

- **Web:** FastAPI (`app.py`) — `GET /`, `POST /process`, `GET /health`
- **Agent loop:** `agent.py` → Anthropic Messages API with tools
- **Model string in code:** `claude-opus-4-7` with `thinking: { type: "adaptive" }`
- **Local tools:** list/read documents, split PDF, validate invoice dicts, export JSON/CSV/Excel, save/copy, send email (mock unless `SMTP_HOST` set)

## Stack

- `anthropic` Python SDK
- FastAPI + Uvicorn
- pdfplumber, pypdf, pandas, Pillow, openpyxl

## Getting started

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
uvicorn app:app --reload
```

Open `http://localhost:8000`.

## Env vars (Railway)

| Variable | Required | Purpose |
|----------|----------|---------|
| `ANTHROPIC_API_KEY` | Yes for live AI | Anthropic API key (`sk-ant-...`) |
| `SMTP_HOST` / related | Optional | Real email instead of mock |

## Deploy

`Procfile` + `railway.toml` included. Prefer Railway for FastAPI.

```bash
railway up
# or link GitHub repo and set ANTHROPIC_API_KEY in Railway Variables
```

## Author

**Harsha Nandhan Reddy**  
GitHub: [@Harshanandhan](https://github.com/Harshanandhan)
