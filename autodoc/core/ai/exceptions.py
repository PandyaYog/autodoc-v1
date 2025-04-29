class LLMException(Exception):
    """Base exception for LLM service errors."""
    pass

class LLMRateLimitError(LLMException):
    """Raised for rate limit errors after retries."""
    pass

class LLMConnectionError(LLMException):
    """Raised for connection errors after retries."""
    pass

class LLMAPIError(LLMException):
    """Raised for non-retryable API errors (e.g., 4xx status codes)."""
    pass