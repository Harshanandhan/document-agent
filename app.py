"""
Document Processing Agent — Web Server
FastAPI app: accepts file uploads + task text, runs the agent, returns results.
Requires ANTHROPIC_API_KEY in the environment for live agent runs.
"""

import os
import uuid
import shutil
import asyncio
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Document Processing Agent",
    description="Lab FastAPI + Claude tool-use document agent (portfolio demo).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

executor = ThreadPoolExecutor(max_workers=10)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "doc_agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def api_key_configured() -> bool:
    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    return bool(key) and key.startswith("sk-ant-")


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/process")
async def process(
    task: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
    if not api_key_configured():
        return JSONResponse(
            {
                "status": "error",
                "result": (
                    "ANTHROPIC_API_KEY is not configured on this server. "
                    "Live Claude agent runs are disabled. "
                    "Set ANTHROPIC_API_KEY in Railway → Variables, redeploy, then retry. "
                    "See GET /health and the sample flow on this page."
                ),
                "api_key_configured": False,
            },
            status_code=503,
        )

    from agent import run_agent

    session_dir = UPLOAD_DIR / str(uuid.uuid4())
    session_dir.mkdir(parents=True)

    try:
        saved_paths = []
        for file in files:
            if file and file.filename:
                safe_name = Path(file.filename).name
                dest = session_dir / safe_name
                with open(dest, "wb") as f:
                    shutil.copyfileobj(file.file, f)
                saved_paths.append(str(dest))

        if saved_paths:
            files_list = ", ".join(f'"{p}"' for p in saved_paths)
            task = f"Files uploaded: {files_list}. Task: {task}"

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            executor,
            lambda: run_agent(task, verbose=False),
        )

        return JSONResponse(
            {"status": "ok", "result": result, "api_key_configured": True}
        )

    except Exception as e:
        return JSONResponse(
            {
                "status": "error",
                "result": str(e),
                "api_key_configured": True,
            },
            status_code=500,
        )

    finally:
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass


@app.get("/health")
async def health():
    key_ok = api_key_configured()
    return {
        "status": "ok",
        "service": "document-agent",
        "api_key_configured": key_ok,
        "live_ai": key_ok,
        "mode": "live_agent" if key_ok else "demo_status_only",
        "endpoints": {
            "ui": "/",
            "health": "/health",
            "process": "POST /process (requires ANTHROPIC_API_KEY)",
        },
        "notes": (
            "Live Claude tool-use agent is available."
            if key_ok
            else "Set ANTHROPIC_API_KEY in Railway env to enable POST /process."
        ),
    }


static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
