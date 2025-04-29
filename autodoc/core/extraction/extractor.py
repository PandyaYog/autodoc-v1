import logging
import os
import io
import zipfile
import fnmatch
from pathlib import Path
from fastapi import UploadFile
from ...config import Settings
from ...utils.security import is_safe_path
from .exceptions import (
    ExtractionSecurityError,
    ExtractionFailedError,
    InvalidFileTypeException
)

logger = logging.getLogger(__name__)

DEFAULT_EXCLUSION_PATTERNS = [
    "__pycache__/*",
    ".git/*",
    "venv/*",
    ".*/",          
    ".*",           
    "*.log",
    "*.tmp",
    "*.bak",
    "*.swp",
    "*.pyc",
    "*.pyo",
]

async def extract_code(
    upload_file: UploadFile,
    target_base_dir: str,
    settings: Settings,
    exclusion_patterns: list[str] = DEFAULT_EXCLUSION_PATTERNS
):
    """
    Extracts Python code securely from an uploaded ZIP file into a target directory.

    Filters out excluded files/directories and non-.py files.

    Args:
        upload_file: The validated file uploaded via FastAPI.
        target_base_dir: The absolute path to the secure temporary directory
                         where files should be extracted. This directory must already exist.
        settings: The application settings instance.
        exclusion_patterns: List of fnmatch patterns to exclude.

    Raises:
        InvalidFileTypeException: If the file cannot be opened as a ZIP.
        ExtractionSecurityError: If an unsafe path is detected in the archive.
        ExtractionFailedError: If any other error occurs during extraction.

    Returns:
        None on successful extraction.
    """
    filename = upload_file.filename or "unknown_file"
    logger.info(f"Starting extraction for '{filename}' into '{target_base_dir}'")
    if not os.path.isdir(target_base_dir):
         logger.error(f"Extraction target directory '{target_base_dir}' does not exist.")
         raise ExtractionFailedError(filename, f"Target directory '{target_base_dir}' not found.")

    try:
        await upload_file.seek(0)
        zip_content = await upload_file.read()
        await upload_file.seek(0)
        with io.BytesIO(zip_content) as zip_buffer:
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                logger.debug(f"Opened '{filename}' as ZipFile. Contains {len(zf.infolist())} members.")

                extracted_count = 0
                skipped_count = 0
                for member_info in zf.infolist():
                    member_path_raw = member_info.filename
                    member_path = member_path_raw.replace('\\', '/')
                    if member_info.is_dir():
                        if any(fnmatch.fnmatch(member_path, pattern + ('/' if not pattern.endswith('/') else '')) for pattern in exclusion_patterns):
                             logger.debug(f"Skipping excluded directory: '{member_path}'")
                             skipped_count += 1
                             continue
                        logger.debug(f"Processing directory entry: '{member_path}' (will be created if needed by file extraction)")

                    if any(fnmatch.fnmatch(member_path, pattern) for pattern in exclusion_patterns):
                        logger.debug(f"Skipping excluded member: '{member_path}'")
                        skipped_count += 1
                        continue

                    is_py_file = not member_info.is_dir() and member_path.lower().endswith('.py')
                    if not member_info.is_dir() and not is_py_file:
                         logger.debug(f"Skipping non-.py file: '{member_path}'")
                         skipped_count += 1
                         continue

                    if not is_safe_path(target_base_dir, member_path):
                        logger.error(f"Unsafe path detected in '{filename}': Member '{member_path}' attempts to escape target directory '{target_base_dir}'.")
                        raise ExtractionSecurityError(filename, member_path, target_base_dir)

                    try:
                        if is_py_file:
                            logger.debug(f"Extracting '{member_path}' to '{target_base_dir}'")
                            zf.extract(member_info, path=target_base_dir)
                            extracted_count += 1
                        
                    except Exception as extract_err:
                        logger.error(f"Error extracting member '{member_path}' from '{filename}': {extract_err}", exc_info=True)
                        raise ExtractionFailedError(filename, f"Error extracting member '{member_path}': {extract_err}")

                logger.info(f"Extraction complete for '{filename}'. Extracted {extracted_count} .py files, skipped {skipped_count} members.")

    except zipfile.BadZipFile:
        logger.error(f"File '{filename}' is not a valid ZIP archive (BadZipFile during extraction).")
        raise InvalidFileTypeException(filename=filename, content_type=upload_file.content_type)
    except ExtractionSecurityError:
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred during extraction of '{filename}': {e}", exc_info=True)
        raise ExtractionFailedError(filename, f"Unexpected error: {e}")
