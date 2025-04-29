# autodoc/core/extraction/validator.py

import logging
import zipfile
import io
from fastapi import UploadFile
import os
from ...config import Settings
from ...utils.security import scan_zip_file_for_malware
from .exceptions import (
    InvalidFileTypeException,
    FileSizeExceededException,
    SecurityScanException,
    ValidationException
)

logger = logging.getLogger(__name__)

EXPECTED_ZIP_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "multipart/x-zip", 
}

async def validate_uploaded_file(upload_file: UploadFile, settings: Settings):
    """
    Validates an uploaded file based on type, size, and security checks.

    Args:
        upload_file: The file uploaded via FastAPI.
        settings: The application settings instance.

    Raises:
        InvalidFileTypeException: If the file is not a valid ZIP archive.
        FileSizeExceededException: If the file size exceeds the configured limit.
        SecurityScanException: If the file fails the security scan.

    Returns:
        None if validation is successful.
    """
    filename = upload_file.filename or "unknown_file"
    logger.info(f"Starting validation for file: '{filename}'")

    # original
    # await upload_file.seek(0)
    # await upload_file.seek(0, io.SEEK_END)
    # file_size = upload_file.tell()
    # await upload_file.seek(0)

    # edited
    file_content = await upload_file.read()
    file_size = len(file_content)
    await upload_file.seek(0)


    if file_size > settings.max_zip_size:
        logger.warning(f"Validation failed for '{filename}': File size {file_size} exceeds limit {settings.max_zip_size}.")
        raise FileSizeExceededException(
            filename=filename,
            file_size=file_size,
            max_size=settings.max_zip_size
        )
    logger.debug(f"File size check passed for '{filename}' ({file_size} bytes).")

    content_type = upload_file.content_type
    if content_type not in EXPECTED_ZIP_MIME_TYPES:
        logger.warning(f"File '{filename}' has unexpected MIME type: '{content_type}'. Proceeding with content check.")

    try:
        file_content = await upload_file.read()
        await upload_file.seek(0) 

        with io.BytesIO(file_content) as file_buffer:
            with zipfile.ZipFile(file_buffer, 'r') as zf:
                if zf.testzip() is not None:
                     logger.error(f"Validation failed for '{filename}': ZIP file integrity check failed (testzip).")
                     raise InvalidFileTypeException(filename=filename, content_type=content_type)
        logger.debug(f"File type check passed for '{filename}': Successfully opened as ZIP.")
    except zipfile.BadZipFile:
        logger.error(f"Validation failed for '{filename}': File is not a valid ZIP archive (BadZipFile).")
        raise InvalidFileTypeException(filename=filename, content_type=content_type)
    except Exception as e:
        logger.error(f"Unexpected error during file type validation for '{filename}': {e}", exc_info=True)
        raise ValidationException(f"Failed to validate file type for '{filename}': {e}")

    temp_file_path = None
    try:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as temp_file:
            await upload_file.seek(0) 
            content_to_write = await upload_file.read()
            temp_file.write(content_to_write)
            temp_file_path = temp_file.name
            logger.debug(f"Saved uploaded file '{filename}' temporarily to '{temp_file_path}' for scanning.")
        await upload_file.seek(0)

        is_safe = scan_zip_file_for_malware(temp_file_path)
        if not is_safe:
            logger.warning(f"Validation failed for '{filename}': Security scan detected potential issues.")
            raise SecurityScanException(filename=filename)
        logger.debug(f"Security scan passed for '{filename}'.")

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Removed temporary scan file: '{temp_file_path}'")
            except OSError as e:
                logger.error(f"Error removing temporary scan file '{temp_file_path}': {e}")


    logger.info(f"Validation successful for file: '{filename}'")
