import logging
import os
import tempfile
import zipfile
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

def is_safe_path(intended_base_dir: str, member_path: str) -> bool:
    """
    Checks if extracting 'member_path' into 'intended_base_dir' is safe.

    Prevents directory traversal attacks (e.g., paths like '../', '/').

    Args:
        intended_base_dir: The absolute path to the secure base directory
                           where extraction is intended.
        member_path: The path of the member file from the archive.

    Returns:
        True if the path is safe, False otherwise.
    """
    try:
        base_dir = Path(intended_base_dir).resolve(strict=True)
        full_path = Path(base_dir / member_path).resolve()
        return base_dir in full_path.parents or base_dir == full_path
    except FileNotFoundError:
        logger.error(f"File not found: {intended_base_dir}")
        return False
    except Exception as e:
        logger.error(f"Error resolving path safety for '{member_path}' in '{intended_base_dir}': {e}", exc_info=True)
        return False

@contextmanager
def create_secure_temp_dir(base_path: Optional[str] = None):
    """
    Creates a secure temporary directory as a context manager.
    Automatically handles cleanup.

    Args:
        base_path: Optional base directory to create temp dir in.

    Yields:
        TemporaryDirectory object (use .name for the path).
    """
    td = tempfile.TemporaryDirectory(dir=base_path)
    logger.info(f"Created secure temporary directory: {td.name}")
    try:
        yield td 
    finally:
        td.cleanup()

def scan_zip_file_for_malware(zip_path: str) -> bool:
    """
    Placeholder for scanning a zip file for known malicious patterns.

    *** This is a basic placeholder and does NOT perform actual scanning. ***
    Integration with tools like ClamAV or cloud-based scanners is recommended
    for production environments but requires additional setup and dependencies.

    Args:
        zip_path: The path to the zip file to be scanned.

    Returns:
        True if the file is considered safe (in this placeholder), False otherwise.
        In a real implementation, False would indicate malware detection.
    """
    logger.warning(f"Malware scanning for '{zip_path}' is currently a placeholder and NOT active.")

    return True
