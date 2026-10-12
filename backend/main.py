"""
FastAPI application for the Data Report Generator.

Provides endpoints for file upload and streaming analysis via SSE.
"""

import logging
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent import run_agent
from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    os.makedirs(config.upload_dir, exist_ok=True)
    logger.info(f"Upload directory: {config.upload_dir}")
    logger.info(f"LLM base URL: {config.base_url}")
    logger.info(f"LLM model: {config.model}")
    yield
    # Shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Data Report Generator",
    description="LLM-powered data analysis report generator",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "model": config.model,
        "base_url": config.base_url,
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload an Excel file for analysis.

    Returns the file ID and path for use with the /api/analyze endpoint.
    """
    if not file.filename:
        return {"error": "No filename provided"}

    # Validate file extension
    allowed_extensions = {".xlsx", ".xls", ".csv"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        return {"error": f"Unsupported file type: {ext}. Allowed: {allowed_extensions}"}

    # Generate unique file ID
    file_id = str(uuid.uuid4())[:8]
    safe_filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(config.upload_dir, safe_filename)

    # Save file
    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    logger.info(f"File uploaded: {file.filename} -> {file_path} ({len(content)} bytes)")

    return {
        "file_id": file_id,
        "filename": file.filename,
        "path": file_path,
        "size": len(content),
    }


@app.post("/api/analyze")
async def analyze(
    file_path: str = Form(...),
    requirement: str = Form(...),
):
    """
    Start analysis and stream results via SSE.

    The agent loop autonomously plans, executes code, and generates
    a comprehensive analysis report with charts and insights.
    """
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    if not requirement.strip():
        return {"error": "Analysis requirement cannot be empty"}

    logger.info(f"Starting analysis: file={file_path}, requirement={requirement[:100]}")

    return StreamingResponse(
        run_agent(file_path, requirement),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )