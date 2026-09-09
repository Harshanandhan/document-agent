# Document Processing Agent

Lab FastAPI + Claude **tool-use** agent for document workflows (PDF/CSV/Excel/images).
Upload files + a task; the agent can call local tools (read, split PDF, validate invoice fields, export, copy, mock/real email).

This is a **portfolio lab**, not a production multi-tenant product.

## What the code actually does

- **Web:** FastAPI (`app.py`) — `GET /`, `POST /process`, `GET /health`
- **Agent loop:** `agent.py` → Anthropic Messages API with tools
- **Model string in code:** `claude-opus-4-7` with `thinking: { type: "adaptive" }` (requires a working `ANTHROPIC_API_KEY`; not proven in the 2026-09-09 evidence pass)
- **Local tools:** list/read documents, split PDF, validate invoice dicts, export JSON/CSV/Excel, save/copy, send email (mock unless `SMTP_HOST` set)
- **Images:** tool path can return base64 image blocks to Claude (vision depends on API/key)

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

CLI:

```bash
python agent.py "Extract invoice data from invoice.pdf and export to JSON"
```

## Evidence (2026-09-09)

```text
import app, agent → ok
run_agent source contains model "claude-opus-4-7" and thinking adaptive
```

**Proven:** package imports; model/tool loop present in source.
**Not proven this run:** live Anthropic call, Railway deploy URL, concurrent "50 users", OCR accuracy, or email delivery.
**Honesty:** older README claimed Claude-powered automation as if production-ready; treat as lab code that needs your own API key.

## Deploy notes

`Procfile` + `railway.toml` exist for Railway-style hosts. Set `ANTHROPIC_API_KEY` there. No live URL verified here.

## Author

**Harsha Nandhan Reddy**  
GitHub: [@Harshanandhan](https://github.com/Harshanandhan)
