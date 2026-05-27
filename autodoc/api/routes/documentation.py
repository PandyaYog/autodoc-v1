"""
Documentation API routes.

POST /generate              — accepts a ZIP, validates synchronously, fires background
                              pipeline, returns 202 immediately with a task_id.
GET  /status/{task_id}      — poll for current task state + download_url when done.
GET  /download/{task_id}    — download the generated PDF once status='completed'.

The heavy pipeline work lives in services/pipeline_runner.py.
"""

import asyncio
import logging
import time
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Request,
    status,
)
from fastapi.responses import Response
from ...config import Settings
from ..deps import get_settings_dependency
from ...core.extraction.validator import validate_uploaded_file
from ...core.extraction.exceptions import (
    ValidationException,
    ExtractionException,
    SecurityScanException,
    InvalidFileTypeException,
    FileSizeExceededException,
    ExtractionSecurityError,
)
from ...models.responses import TaskAcceptedResponse, TaskStatusResponse, ErrorResponse
from ...models.settings import Settings
from ...services.task_store import task_store
from ...services.pipeline_runner import run_documentation_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/generate",
    response_model=TaskAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Generate Documentation from Python Codebase",
    description=(
        "Upload a ZIP file containing a Python codebase. "
        "The file is validated immediately; if it passes, a background task is started "
        "and a task_id is returned. Poll GET /status/{task_id} to check progress and "
        "retrieve the generated Markdown documentation when ready."
    ),
    tags=["Documentation"],
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid file type or empty ZIP",
            "model": ErrorResponse,
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "description": "File size exceeds the configured limit",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "File failed validation (corrupt ZIP, security scan, etc.)",
            "model": ErrorResponse,
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Unexpected server error during validation",
            "model": ErrorResponse,
        },
    },
)
async def generate_documentation(
    upload_file: UploadFile = File(..., description="A ZIP file containing the Python codebase."),
    settings: Settings = Depends(get_settings_dependency),
):
    """
    Accepts a ZIP upload, validates it, and starts a background documentation task.

    Synchronous steps (done before returning 202):
      1. File type + size validation.
      2. ZIP integrity check.
      3. Malware scan (placeholder).

    Asynchronous steps (run in the background — do not block the response):
      4. File extraction into a secure temp directory.
      5. Code Knowledge Graph construction.
      6. CKG edge resolution (imports, calls, inheritance).
      7. AI summarization of every CKG node.
      8. Markdown document assembly.
    """
    original_filename = upload_file.filename or "uploaded_codebase.zip"
    logger.info(f"Received upload request for: '{original_filename}'")

    # ── Step 1: Validate synchronously ────────────────────────────────────────
    # Validation runs NOW so invalid files get an immediate error, not a 202
    # that later flips to "failed" in the task store.
    try:
        await validate_uploaded_file(upload_file, settings)
        logger.info(f"Validation passed for: '{original_filename}'")
    except InvalidFileTypeException as e:
        logger.warning(f"Invalid file type: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileSizeExceededException as e:
        logger.warning(f"File too large: {e}")
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except SecurityScanException as e:
        logger.warning(f"Security scan failed: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Input validation failed: {e}",
        )
    except Exception as e:
        logger.critical(f"Unexpected error during validation for '{original_filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error during file validation: {type(e).__name__}",
        )

    # ── Step 2: Read the file bytes ───────────────────────────────────────────
    # validate_uploaded_file() reads the stream internally. We seek back to
    # the beginning so we can read the full bytes to hand off to the background
    # task. File objects cannot be passed across asyncio task boundaries.
    await upload_file.seek(0)
    file_bytes = await upload_file.read()

    # ── Step 3: Register task ─────────────────────────────────────────────────
    task_id = task_store.create(filename=original_filename)
    logger.info(f"Registered task '{task_id}' for '{original_filename}'.")

    # ── Step 4: Launch background pipeline ────────────────────────────────────
    # asyncio.create_task() schedules the coroutine on the current event loop
    # and returns immediately — it does NOT await the pipeline.
    asyncio.create_task(
        run_documentation_pipeline(
            task_id=task_id,
            file_bytes=file_bytes,
            filename=original_filename,
        ),
        name=f"pipeline-{task_id}",  # named for easier debugging in logs
    )
    logger.info(f"Background pipeline task launched for task_id='{task_id}'.")

    # ── Step 5: Return 202 immediately ────────────────────────────────────────
    return TaskAcceptedResponse(
        task_id=task_id,
        status="pending",
        message=(
            f"Documentation generation started for '{original_filename}'. "
            f"Poll GET /api/v1/status/{task_id} to check progress."
        ),
    )


@router.get(
    "/status/{task_id}",
    response_model=TaskStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Check Documentation Task Status",
    description=(
        "Poll this endpoint with the task_id returned by POST /generate. "
        "Returns the current state of the background task and — once complete — "
        "the full Markdown documentation."
    ),
    tags=["Documentation"],
    responses={
        status.HTTP_404_NOT_FOUND: {
            "description": "No task found with the given task_id",
            "model": ErrorResponse,
        },
    },
)
async def get_task_status(task_id: str, request: Request):
    """
    Returns the current state of a documentation generation task.

    Possible status values:
      - **pending**    — task is queued, pipeline has not started yet.
      - **processing** — pipeline is actively running.
      - **completed**  — PDF is ready; use the download_url to fetch it.
      - **failed**     — pipeline encountered an error; `error` field contains the reason.
    """
    record = task_store.get(task_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found. It may have expired or the ID is incorrect.",
        )

    # Build the download URL dynamically from the incoming request so it works
    # on any host/port without hardcoding (localhost, deployed domain, etc.)
    download_url = None
    if record.status == "completed" and record.pdf_bytes is not None:
        base = str(request.base_url).rstrip("/")
        download_url = f"{base}/api/v1/download/{task_id}"

    return TaskStatusResponse(
        task_id=record.task_id,
        status=record.status,
        filename=record.filename,
        download_url=download_url,
        error=record.error,
        markdown=record.documentation if record.status == "completed" else None,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get(
    "/download/{task_id}",
    status_code=status.HTTP_200_OK,
    summary="Download Generated Documentation PDF",
    description=(
        "Download the PDF documentation generated for a completed task. "
        "Use the download_url returned by GET /status/{task_id} or call this "
        "endpoint directly once you know the task is completed."
    ),
    tags=["Documentation"],
    responses={
        status.HTTP_200_OK: {
            "description": "PDF file download",
            "content": {"application/pdf": {}},
        },
        status.HTTP_404_NOT_FOUND: {
            "description": "Task not found",
            "model": ErrorResponse,
        },
        status.HTTP_400_BAD_REQUEST: {
            "description": "Task is not yet completed (still pending or processing)",
            "model": ErrorResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Task completed but PDF rendering failed",
            "model": ErrorResponse,
        },
    },
)
async def download_documentation(task_id: str):
    """
    Returns the PDF documentation for a completed task as a binary file download.

    The PDF is streamed directly from in-memory bytes — no temp file is created.
    Content-Disposition is set to 'attachment' so browsers trigger a save dialog.
    """
    record = task_store.get(task_id)

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found. It may have expired or the ID is incorrect.",
        )

    if record.status in ("pending", "processing"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Task '{task_id}' is still {record.status}. "
                f"Poll GET /api/v1/status/{task_id} and retry when status='completed'."
            ),
        )

    if record.status == "failed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Task '{task_id}' failed: {record.error}",
        )

    # status == 'completed' but pdf_bytes is None means rendering failed
    if record.pdf_bytes is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Task '{task_id}' completed successfully but PDF rendering failed. "
                f"The documentation was generated but could not be converted to PDF."
            ),
        )

    # Build a safe filename from the original uploaded filename
    safe_name = (record.filename or "documentation").removesuffix(".zip").removesuffix(".ZIP")
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in safe_name)
    download_filename = f"{safe_name}_documentation.pdf"

    logger.info(
        f"[Download] Serving PDF for task '{task_id}' "
        f"({len(record.pdf_bytes):,} bytes) as '{download_filename}'."
    )

    return Response(
        content=record.pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{download_filename}"',
            "Content-Length": str(len(record.pdf_bytes)),
        },
    )