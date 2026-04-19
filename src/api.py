"""FastAPI server — Serves podcast MP3 files and provides health/latest endpoints."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output")).resolve()
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Strict allow-list: YYYY-MM-DD only (no path separators, no dots, no special chars)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="NewsCast-AI API", version="1.0.0")


def _safe_date_dir(date: str) -> tuple[str, Path]:
    """Validate *date*, then build a safe directory path from the parsed date object.

    Returns a (canonical_date_str, resolved_path) tuple so that the path is
    constructed from a trusted (parsed & reformatted) value — not from raw user input.
    Raises HTTPException(400) for invalid dates.
    """
    if not _DATE_RE.match(date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    try:
        parsed = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Reconstruct from the parsed object — no longer tainted by user input
    canonical = parsed.strftime("%Y-%m-%d")
    resolved = (OUTPUT_DIR / canonical).resolve()

    # Belt-and-suspenders: reject any path that escapes OUTPUT_DIR
    if not resolved.is_relative_to(OUTPUT_DIR):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    return canonical, resolved


@app.get("/podcasts/{date}.mp3", response_class=FileResponse)
async def get_podcast(date: str) -> FileResponse:
    """Download the podcast MP3 for a given date (YYYY-MM-DD)."""
    canonical, date_dir = _safe_date_dir(date)

    if not date_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"No podcast found for {canonical}")

    mp3_files = sorted(date_dir.glob("*.mp3"))
    if not mp3_files:
        raise HTTPException(status_code=404, detail=f"No podcast found for {canonical}")

    return FileResponse(
        path=str(mp3_files[0]),
        media_type="audio/mpeg",
        filename=f"podcast-{canonical}.mp3",
    )


@app.get("/health")
async def health() -> JSONResponse:
    """Healthcheck — verifies that Ollama is reachable."""
    ollama_ok = False
    ollama_status = "unreachable"
    try:
        resp = requests.get(OLLAMA_URL, timeout=5)
        ollama_ok = resp.status_code == 200
        ollama_status = "ok" if ollama_ok else f"http_{resp.status_code}"
    except requests.RequestException:
        ollama_status = "unreachable"

    return JSONResponse(
        status_code=200 if ollama_ok else 503,
        content={"status": "ok" if ollama_ok else "degraded", "ollama": ollama_status},
    )


@app.get("/latest")
async def latest() -> RedirectResponse:
    """Redirect to the most recent available podcast."""
    # Look back up to 30 days for the latest podcast
    for days_ago in range(0, 30):
        # Build the date from a trusted datetime object — not from user input
        date_dir = (OUTPUT_DIR / (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d")).resolve()
        if date_dir.is_relative_to(OUTPUT_DIR) and date_dir.is_dir() and list(date_dir.glob("*.mp3")):
            date_str = date_dir.name
            return RedirectResponse(url=f"/podcasts/{date_str}.mp3", status_code=307)

    raise HTTPException(status_code=404, detail="No podcast available yet")
