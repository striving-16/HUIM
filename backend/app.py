"""
backend/app.py — FastAPI backend for HUIM on Spark.

Flow: Vercel frontend --upload/run-huim/results--> this API --> Spark HUIM
engine (core.huim_miner.run_huim) --> JSON results --> frontend.

This layer only does I/O and orchestration: it saves uploaded files,
calls run_huim(dataset_path), and returns JSON. It never re-implements
or touches the mining algorithm itself.

Run locally:
    uvicorn backend.app:app --reload --port 8000
"""

import os
import re
import sys
import tempfile
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# core.huim_miner logs mining progress with emoji (✅, 🚀, ...). On consoles
# stuck on a non-UTF-8 codepage (e.g. Windows cp1252 under uvicorn) those
# prints raise UnicodeEncodeError and turn into a 500 on every request.
# Replacing unencodable characters instead of crashing keeps the API alive
# regardless of the host's terminal encoding.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

# Make the project root importable (core/, infrastructure/, domain/)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from core.huim_miner import run_huim  # noqa: E402

ALLOWED_EXTENSIONS = {".txt", ".csv"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB — comfortably above a 100K-line dataset

# Uploaded datasets are stored outside the repo (works on read-only/ephemeral
# deploy filesystems too). Override with HUIM_UPLOAD_DIR if you need a fixed path.
UPLOAD_DIR = os.environ.get("HUIM_UPLOAD_DIR") or os.path.join(tempfile.gettempdir(), "huim_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="HUIM on Spark — Backend API", version="1.0.0")

# CORS: allow the Vercel frontend to call this API. Set ALLOWED_ORIGINS to a
# comma-separated list of origins in production (e.g. https://your-app.vercel.app).
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
_allow_origins = ["*"] if _origins_env.strip() == "*" else [o.strip() for o in _origins_env.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,  # no cookies/auth used — safe to pair with "*"
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache of the last computed result, for GET /results.
# Single-process only: fine for one backend instance; swap for a real store
# (DB/Redis) if you scale to multiple workers/instances.
_last_result: Optional[dict] = None


class RunHuimRequest(BaseModel):
    filename: str
    min_util: float = 5.0
    mode: Literal["local", "spark"] = "local"


def _sanitize_filename(filename: str) -> str:
    """Strip path components and unsafe characters from an uploaded filename."""
    name = os.path.basename(filename)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "dataset.txt"


@app.get("/")
def health():
    return {"service": "huim-backend", "status": "ok"}


@app.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    """Receive a dataset file and store it, ready for /run-huim."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'. Use .txt or .csv.")

    safe_name = _sanitize_filename(file.filename)
    dest_path = os.path.join(UPLOAD_DIR, safe_name)

    size = 0
    try:
        with open(dest_path, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="File too large (max 50MB).")
                out.write(chunk)
    finally:
        await file.close()

    return {
        "success": True,
        "filename": safe_name,
        "size_bytes": size,
    }


@app.post("/run-huim")
def run_huim_endpoint(request: RunHuimRequest):
    """Trigger Spark HUIM processing on a previously uploaded dataset."""
    global _last_result

    dataset_path = os.path.join(UPLOAD_DIR, _sanitize_filename(request.filename))
    if not os.path.exists(dataset_path):
        raise HTTPException(status_code=404, detail=f"Dataset '{request.filename}' not found. Upload it first.")

    if request.min_util <= 0:
        raise HTTPException(status_code=400, detail="min_util must be > 0.")

    try:
        result = run_huim(dataset_path, min_util=request.min_util, mode=request.mode)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"HUIM processing failed: {e}") from e

    result["filename"] = request.filename
    _last_result = result
    return result


@app.get("/results")
def get_last_results():
    """Return the last computed HUIM result."""
    if _last_result is None:
        raise HTTPException(status_code=404, detail="No results yet. Call /run-huim first.")
    return _last_result
