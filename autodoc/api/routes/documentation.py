import logging
import tempfile
import time
from typing import Union
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    status,
)
from ...config import Settings
from ..deps import get_settings_dependency
from ...core.extraction.validator import validate_uploaded_file
from ...core.extraction.extractor import extract_code
from ...core.extraction.exceptions import (
    ValidationException,
    ExtractionException,
    SecurityScanException,
    InvalidFileTypeException,
    FileSizeExceededException,
    ExtractionSecurityError
)
from ...core.ckg.traversal import build_ckg_from_path
from ...core.ckg.resolver import resolve_ckg_edges
from ...core.ai.summarizer import generate_summaries 
from ...core.document.assembler import DocumentAssembler
from ...models.responses import SuccessResponse, ErrorResponse
from ...models.settings import Settings 
from ...utils.security import create_secure_temp_dir

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post(
    "/generate",
    response_model=SuccessResponse, 
    summary="Generate Documentation from Python Codebase",
    description="Upload a ZIP file containing a Python codebase. The API will analyze the code, "
                "build a knowledge graph, generate summaries using an LLM, and return the "
                "compiled documentation in Markdown format.",
    tags=["Documentation"],
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Bad Request (e.g., Invalid file type, Security scan failed)",
            "model": ErrorResponse,
        },
        status.HTTP_413_REQUEST_ENTITY_TOO_LARGE: {
            "description": "File size exceeds limit",
            "model": ErrorResponse,
        },
        status.HTTP_422_UNPROCESSABLE_ENTITY: {
            "description": "Validation Error (specific details if applicable)",
            "model": ErrorResponse, 
        },
        status.HTTP_500_INTERNAL_SERVER_ERROR: {
            "description": "Internal Server Error during processing",
            "model": ErrorResponse,
        },
    },
)
async def generate_documentation(
    upload_file: UploadFile = File(..., description="A ZIP file containing the Python codebase."),
    settings: Settings = Depends(get_settings_dependency),
):
    """
    Main endpoint to handle documentation generation requests.
    """
    start_time = time.time()
    filename = upload_file.filename or "uploaded_file.zip"
    logger.info(f"Received request to generate documentation for: {filename}")

    temp_dir_obj = None

    try:
        logger.debug(f"Validating file: {filename}")
        await validate_uploaded_file(upload_file, settings)
        logger.info(f"Validation successful for: {filename}")

        logger.debug("Creating secure temporary directory...")
        with create_secure_temp_dir(base_path=settings.temp_dir_base) as temp_dir_obj:
            extraction_path = temp_dir_obj.name
            logger.info(f"Extracting '{filename}' to temporary directory: {extraction_path}")

            await upload_file.seek(0)
            await extract_code(upload_file, extraction_path, settings)
            logger.info(f"Extraction successful for: {filename}")

            logger.info("Starting CKG construction (traversal)...")
            ckg = build_ckg_from_path(extraction_path)
            if len(ckg) == 0:
                 logger.warning("CKG construction resulted in an empty graph.")
                 
            logger.info("Starting CKG edge resolution...")
            resolve_ckg_edges(ckg)

            logger.info("Starting AI summarization...")
            await generate_summaries(ckg, settings)
            logger.info("AI summarization completed.")

            logger.info("Starting final document assembly...")
            assembler = DocumentAssembler(ckg)
            markdown_content = assembler.assemble()
            logger.info("Document assembly completed.")

            end_time = time.time()
            processing_time = end_time - start_time
            logger.info(f"Successfully generated documentation for '{filename}' in {processing_time:.2f} seconds.")
            return SuccessResponse(
                documentation=markdown_content,
                message=f"Documentation generated successfully for {filename}."
            )

    except InvalidFileTypeException as e:
        logger.error(f"Invalid file type error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except FileSizeExceededException as e:
         logger.error(f"File size exceeded error: {e}")
         raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(e))
    except SecurityScanException as e:
         logger.error(f"Security scan failed: {e}")
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ValidationException as e: 
        logger.error(f"Validation error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Input validation failed: {e}")
    except ExtractionSecurityError as e:
        logger.error(f"Extraction security error: {e}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Extraction failed due to security concerns: {e}")
    except ExtractionException as e:
        logger.error(f"Extraction error: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Code extraction failed: {e}")
    except HTTPException:
         raise
    except Exception as e:
        logger.critical(f"Unexpected internal server error during documentation generation for '{filename}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during documentation generation: {type(e).__name__}",
        )

    # Note: No explicit finally block needed for temp_dir cleanup IF the core processing
    # happens *inside* the 'with create_secure_temp_dir(...) as temp_dir_obj:' block.
    # The context manager handles cleanup on exit, even if exceptions occur.