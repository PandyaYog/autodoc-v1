"""
Pipeline Runner — background documentation generation task.

Provides:
  - _BytesUploadFile: minimal async adapter so raw bytes can be passed to
    extract_code() (which expects a FastAPI UploadFile interface).
  - run_documentation_pipeline(): the standalone async function launched by
    asyncio.create_task(). It owns the full pipeline after validation:
      extract → CKG build → edge resolution → AI summarization → assembly.

Design contract:
  - This function NEVER raises. All exceptions are caught and recorded in the
    task store via task_store.mark_failed(). This is required so that
    asyncio.create_task() does not silently swallow unhandled exceptions and
    crash the event loop.
  - The function accepts raw bytes (not an UploadFile) because file objects
    cannot safely be passed across asyncio task boundaries — the underlying
    stream may be closed by the time the task runs.
"""

import io
import logging
import time
from typing import Optional

from ..config import settings
from ..core.extraction.extractor import extract_code
from ..core.extraction.exceptions import ExtractionException, ExtractionSecurityError
from ..core.ckg.traversal import build_ckg_from_path
from ..core.ckg.resolver import resolve_ckg_edges
from ..core.ai.summarizer import generate_summaries
from ..core.document.assembler import DocumentAssembler
from ..core.document.renderer import render_to_pdf
from ..utils.security import create_secure_temp_dir
from .task_store import task_store

logger = logging.getLogger(__name__)


# ── Bytes-to-UploadFile adapter ───────────────────────────────────────────────

class _BytesUploadFile:
    """
    Minimal async adapter that wraps raw bytes into the UploadFile interface
    expected by extract_code() and validate_uploaded_file().

    Only implements the methods actually called by those functions:
      - read()  → returns all bytes
      - seek()  → moves the internal buffer cursor

    This keeps the runner self-contained without changing the extractor's API.
    """

    def __init__(self, filename: str, content: bytes, content_type: str = "application/zip") -> None:
        self.filename = filename
        self.content_type = content_type
        self._buffer = io.BytesIO(content)

    async def read(self) -> bytes:
        """Returns the full content bytes (position-independent)."""
        return self._buffer.getvalue()

    async def seek(self, offset: int, whence: int = 0) -> int:
        """Moves buffer cursor. Mirrors SpooledTemporaryFile.seek() semantics."""
        return self._buffer.seek(offset, whence)


# ── Background pipeline ───────────────────────────────────────────────────────

async def run_documentation_pipeline(
    task_id: str,
    file_bytes: bytes,
    filename: str,
) -> None:
    """
    Full documentation generation pipeline, designed to run as a background task.

    Call via:
        asyncio.create_task(run_documentation_pipeline(task_id, file_bytes, filename))

    Pipeline stages:
        1. Extract .py / config files from the ZIP into a secure temp directory.
        2. Validate that at least one supported file was found.
        3. Build the Code Knowledge Graph (CKG) via AST traversal.
        4. Resolve cross-file edges (imports, calls, inheritance).
        5. Generate AI summaries for every CKG node (bottom-up, concurrent).
        6. Assemble the final Markdown document from the annotated CKG.
        7. Store the result (or error) in the task store.

    Args:
        task_id:    The task store ID to update throughout execution.
        file_bytes: Raw bytes of the already-validated ZIP file.
        filename:   Original filename — used for logging and error messages.

    Returns:
        None. This function never raises. Results are written to task_store.
    """
    task_store.mark_processing(task_id)
    start_time = time.time()
    logger.info(
        f"[Pipeline:{task_id}] Background pipeline started for '{filename}'."
    )

    markdown_content: Optional[str] = None
    pdf_bytes: Optional[bytes] = None

    try:
        # Wrap raw bytes in the UploadFile-compatible adapter
        mock_file = _BytesUploadFile(filename=filename, content=file_bytes)

        with create_secure_temp_dir(base_path=settings.temp_dir_base) as temp_dir_obj:
            extraction_path = temp_dir_obj.name

            # ── Stage 1: Extract ──────────────────────────────────────────
            logger.info(f"[Pipeline:{task_id}] Extracting files to '{extraction_path}'...")
            extraction_stats = await extract_code(mock_file, extraction_path, settings)

            extracted_count      = extraction_stats.get("extracted_count", 0)
            js_ts_extracted_count = extraction_stats.get("js_ts_extracted_count", 0)
            config_extracted_count = extraction_stats.get("config_extracted_count", 0)
            non_python_count     = extraction_stats.get("non_python_count", 0)
            total_extracted      = extracted_count + js_ts_extracted_count + config_extracted_count

            # ── Stage 2: Validate extraction counts ───────────────────────
            if total_extracted == 0:
                if non_python_count > 0:
                    error_msg = (
                        f"No supported files found in '{filename}'. "
                        f"Found {non_python_count} unsupported file(s). "
                        f"AutoDoc AI supports Python and React (JS/TS) codebases with optional "
                        f".md, .txt, .yaml, .toml, and Dockerfile files."
                    )
                else:
                    error_msg = (
                        f"No files found in '{filename}'. "
                        f"The ZIP archive appears to be empty or contains only directories."
                    )
                logger.warning(f"[Pipeline:{task_id}] Extraction yielded no files: {error_msg}")
                task_store.mark_failed(task_id, error_msg)
                return  # temp dir cleaned up by context manager on exit

            logger.info(
                f"[Pipeline:{task_id}] Extraction complete — "
                f"{extracted_count} .py, {js_ts_extracted_count} .js/.ts, {config_extracted_count} config/doc files."
            )

            # ── Stage 3: Build CKG ────────────────────────────────────────
            logger.info(f"[Pipeline:{task_id}] Building Code Knowledge Graph...")
            ckg = build_ckg_from_path(extraction_path, root_name=filename)
            if len(ckg) == 0:
                logger.warning(f"[Pipeline:{task_id}] CKG traversal produced an empty graph.")

            # ── Stage 4: Resolve edges ────────────────────────────────────
            logger.info(f"[Pipeline:{task_id}] Resolving CKG edges...")
            resolve_ckg_edges(ckg)

            # ── Stage 5: AI summarization ─────────────────────────────────
            logger.info(f"[Pipeline:{task_id}] Starting AI summarization...")
            await generate_summaries(ckg, settings)
            logger.info(f"[Pipeline:{task_id}] AI summarization complete.")

            # ── Stage 6: Assemble Markdown ────────────────────────────────
            logger.info(f"[Pipeline:{task_id}] Assembling Markdown document...")
            assembler = DocumentAssembler(ckg)
            markdown_content = assembler.assemble()
            logger.info(f"[Pipeline:{task_id}] Document assembly complete.")

        # context manager has exited — temp dir is now cleaned up
        elapsed = time.time() - start_time
        logger.info(
            f"[Pipeline:{task_id}] Pipeline finished in {elapsed:.2f}s for '{filename}'."
        )

        # ── Stage 7: Render PDF ───────────────────────────────────────────────
        # Runs OUTSIDE the temp dir context — only needs the Markdown string.
        # Isolated try/except: a PDF render failure does NOT fail the whole task.
        # The task is still marked completed; the download endpoint handles the
        # degraded state by returning a 503 if pdf_bytes is None.
        logger.info(f"[Pipeline:{task_id}] Rendering PDF...")
        try:
            project_name = filename.removesuffix(".zip").removesuffix(".ZIP")
            pdf_bytes = render_to_pdf(markdown_content, project_name=project_name)
            logger.info(f"[Pipeline:{task_id}] PDF rendered ({len(pdf_bytes):,} bytes).")
        except Exception as render_err:
            logger.error(
                f"[Pipeline:{task_id}] PDF rendering failed — Markdown is still available. "
                f"{type(render_err).__name__}: {render_err}",
                exc_info=True,
            )
            pdf_bytes = None  # degraded: completed without PDF

        # ── Stage 8: Store result ─────────────────────────────────────────────
        task_store.mark_completed(task_id, markdown_content, pdf_bytes=pdf_bytes)


    # ── Specific error handlers ───────────────────────────────────────────────

    except ExtractionSecurityError as e:
        error_msg = f"Security error during extraction: {e}"
        logger.error(f"[Pipeline:{task_id}] {error_msg}")
        task_store.mark_failed(task_id, error_msg)

    except ExtractionException as e:
        error_msg = f"File extraction failed: {e}"
        logger.error(f"[Pipeline:{task_id}] {error_msg}", exc_info=True)
        task_store.mark_failed(task_id, error_msg)

    except Exception as e:
        # Catch-all: ensures asyncio.create_task() never sees an unhandled exception
        error_msg = f"An unexpected error occurred: {type(e).__name__}: {e}"
        logger.critical(f"[Pipeline:{task_id}] {error_msg}", exc_info=True)
        task_store.mark_failed(task_id, error_msg)
