class ValidationException(ValueError):
    """Base class for validation errors."""
    pass

class InvalidFileTypeException(ValidationException):
    """Raised when the uploaded file is not a valid ZIP archive."""
    def __init__(self, filename: str, content_type: str | None):
        self.filename = filename
        self.content_type = content_type
        super().__init__(f"File '{filename}' is not a valid ZIP archive (reported type: {content_type}).")

class FileSizeExceededException(ValidationException):
    """Raised when the uploaded file exceeds the maximum allowed size."""
    def __init__(self, filename: str, file_size: int, max_size: int):
        self.filename = filename
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"File '{filename}' size ({file_size} bytes) exceeds maximum limit ({max_size} bytes).")

class SecurityScanException(ValidationException):
    """Raised when the file fails a security check (e.g., malware scan)."""
    def __init__(self, filename: str, reason: str = "Security scan failed"):
        self.filename = filename
        self.reason = reason
        super().__init__(f"File '{filename}' failed security check: {reason}")

class ExtractionException(Exception):
    """Base class for extraction errors."""
    pass

class ExtractionSecurityError(ExtractionException):
    """Raised when a potentially unsafe path is detected during extraction."""
    def __init__(self, filename: str, member_path: str, target_dir: str):
        self.filename = filename
        self.member_path = member_path
        self.target_dir = target_dir
        super().__init__(f"Security error extracting '{member_path}' from '{filename}' into '{target_dir}': Path is unsafe.")

class ExtractionFailedError(ExtractionException):
    """Raised when a general error occurs during extraction."""
    def __init__(self, filename: str, reason: str):
        self.filename = filename
        self.reason = reason
        super().__init__(f"Failed to extract '{filename}': {reason}")