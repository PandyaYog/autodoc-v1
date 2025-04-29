import asyncio
import logging
from typing import Optional
from groq import AsyncGroq, RateLimitError, APIConnectionError, APIStatusError
from ..config import settings
from ..core.ai.exceptions import LLMException, LLMRateLimitError, LLMConnectionError, LLMAPIError 
import re
import time

logger = logging.getLogger(__name__)

MAX_OTHER_ERROR_RETRIES: int = 10
INITIAL_RETRY_DELAY: float = 10.0
MAX_RETRY_DELAY: float = 100.0
DEFAULT_RATE_LIMIT_DELAY: float = 500.0
RATE_LIMIT_DELAY_BUFFER: float = 0.5


def _parse_retry_after(error_message: str) -> Optional[float]:
    """Attempts to parse the suggested retry delay from Groq's error message."""
    match = re.search(r"try again in (\d+(\.\d+)?)\s*s", error_message, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

class GroqLLMService:
    """
    A service class to interact with the Groq LLM API asynchronously.

    Handles client initialization, API calls, basic error handling, and retries.
    """

    _client: Optional[AsyncGroq] = None

    @classmethod
    def _get_client(cls) -> AsyncGroq:
        """Initializes and returns the async Groq client (singleton pattern)."""
        if cls._client is None:
            if not settings.groq_api_key_value:
                raise LLMConnectionError("Groq API key is not configured.")
            try:
                logger.info(f"Initializing AsyncGroq client for model {settings.groq_model_name}")
                cls._client = AsyncGroq(
                    api_key=settings.groq_api_key_value,
                    timeout=settings.request_timeout,
                    max_retries=0
                )
            except Exception as e:
                logger.critical(f"Failed to initialize Groq client: {e}", exc_info=True)
                raise LLMConnectionError(f"Failed to initialize Groq client: {e}")
        return cls._client

    async def generate_summary(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 500, 
    ) -> Optional[str]: 
        """
        Generates a summary using the configured Groq model with persistent retries for rate limits.

        Args:
            prompt: The formatted prompt string.
            model_name: Override the default model from settings if needed.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate for the summary.

        Returns:
            The generated summary string, or None if generation fails due to
            non-retryable errors or exceeds retries for non-rate-limit errors.

        Raises:
            LLMConnectionError: If connection issues persist after limited retries.
            LLMAPIError: For non-retryable API errors (e.g., bad request, auth).
            LLMException: For unexpected errors after limited retries.
        """
        client = self._get_client()
        target_model = model_name or settings.groq_model_name
        other_error_retry_count = 0
        current_delay = INITIAL_RETRY_DELAY

        while True: 
            try:
                logger.debug(f"Sending request to Groq model {target_model}. Prompt length: {len(prompt)}")
                start_llm_call = time.time()
                chat_completion = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                end_llm_call = time.time()
                duration = end_llm_call - start_llm_call

                if chat_completion.choices and chat_completion.choices[0].message:
                    summary = chat_completion.choices[0].message.content
                    usage = chat_completion.usage
                    logger.debug(
                         f"Groq response received in {duration:.2f}s. "
                         f"Tokens: Prompt={usage.prompt_tokens if usage else 'N/A'}, Completion={usage.completion_tokens if usage else 'N/A'}. "
                         f"Summary Length: {len(summary or '')}"
                     )
                    if summary:
                        return summary.strip()
                    else:
                        logger.warning(f"Groq model {target_model} returned an empty summary.")
                        raise LLMException("LLM returned an empty summary.")

                else:
                    logger.error(f"Invalid response structure received from Groq API: {chat_completion}")
                    raise LLMException("Invalid response structure received from LLM.")

            except RateLimitError as e:
                error_body = e.body.get('error', {}) if e.body else {}
                error_message = error_body.get('message', str(e))
                logger.warning(f"Rate limit hit for Groq API: {error_message}")

                wait_time = _parse_retry_after(error_message)
                if wait_time is None:
                    wait_time = DEFAULT_RATE_LIMIT_DELAY 
                    logger.info(f"Could not parse specific delay from rate limit message. Waiting default {wait_time:.2f}s...")
                else:
                    wait_time += RATE_LIMIT_DELAY_BUFFER 
                    logger.info(f"Groq suggested waiting. Waiting for {wait_time:.2f}s...")

                await asyncio.sleep(wait_time)
                other_error_retry_count = 0
                current_delay = INITIAL_RETRY_DELAY
                continue 
            except APIConnectionError as e:
                logger.warning(f"Connection error with Groq API (Attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}). Retrying in {current_delay:.2f}s...")
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                    logger.error("Max retries reached for connection error.")
                    return None
                    
                other_error_retry_count += 1

            except APIStatusError as e:
                 if e.status_code >= 500 and other_error_retry_count < MAX_OTHER_ERROR_RETRIES:
                     logger.warning(f"Groq API server error (Status {e.status_code}, Attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}). Retrying in {current_delay:.2f}s...")
                     other_error_retry_count += 1
                 else:
                     logger.error(f"Non-retryable Groq API status error: {e.status_code} - {e.message}", exc_info=False)
                     return None
                     
            except Exception as e:
                logger.warning(f"Unexpected error during Groq API call (Attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}): {e}", exc_info=True)
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                     logger.error("Max retries reached for unexpected error.")
                     return None
                     
                other_error_retry_count += 1

            logger.debug(f"Sleeping for {current_delay:.2f}s before retrying non-rate-limit error...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RETRY_DELAY)

    async def close_client(self):
        """Closes the underlying Groq client connection if initialized."""
        if GroqLLMService._client:
            try:
                await GroqLLMService._client.aclose() 
                logger.info("Closed AsyncGroq client connection.")
                GroqLLMService._client = None
            except Exception as e:
                logger.error(f"Error closing Groq client: {e}", exc_info=True)