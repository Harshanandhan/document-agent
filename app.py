"""
Document Processing Agent — Web Server
FastAPI app: accepts file uploads + task text, runs the agent, returns results.
50 users share one Anthropic API key set as an environment variable on Railway.
"""

import os
import uuid
import shutil
import asyncio
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from agent import run_agent

app = FastAPI(title="Document Processing Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Thread pool so multiple users can run agents concurrently
executor = ThreadPoolExecutor(max_workers=10)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "doc_agent_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.post("/process")
async def process(
    task: str = Form(...),
    files: list[UploadFile] = File(default=[]),
):
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
            lambda: run_agent(task, verbose=False)
        )

        return JSONResponse({"status": "ok", "result": result})

    except Exception as e:
        return JSONResponse({"status": "error", "result": str(e)}, status_code=500)

    finally:
        try:
            shutil.rmtree(session_dir, ignore_errors=True)
        except Exception:
            pass


@app.get("/health")
async def health():
    key_set = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"status": "ok", "api_key_configured": key_set}


# Mount static files (for any additional assets)
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
