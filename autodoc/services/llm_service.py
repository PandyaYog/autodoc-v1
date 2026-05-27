"""
LLM Service module.

Provides a unified interface (BaseLLMService) for LLM providers, concrete
implementations (GroqLLMService, GeminiLLMService), and a factory function
(get_llm_service) that returns the correct backend based on settings.

To add a new provider:
  1. Subclass BaseLLMService and implement generate_summary() and close_client().
  2. Register it in get_llm_service().
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Optional

from ..config import settings
from ..core.ai.exceptions import LLMException, LLMRateLimitError, LLMConnectionError, LLMAPIError

logger = logging.getLogger(__name__)

# ── Shared retry constants ────────────────────────────────────────────────────
MAX_OTHER_ERROR_RETRIES: int = 10
INITIAL_RETRY_DELAY: float = 10.0
MAX_RETRY_DELAY: float = 100.0
DEFAULT_RATE_LIMIT_DELAY: float = 500.0
RATE_LIMIT_DELAY_BUFFER: float = 0.5


def _parse_retry_after(error_message: str) -> Optional[float]:
    """Attempts to parse the suggested retry delay from an error message."""
    match = re.search(r"try again in (\d+(\.\d+)?)\s*s", error_message, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseLLMService(ABC):
    """
    Abstract base class for all LLM service backends.

    Every provider (Groq, Gemini, …) must implement:
      - generate_summary(): the core LLM call
      - close_client():     graceful shutdown of the underlying HTTP client
    """

    @abstractmethod
    async def generate_summary(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """
        Sends a prompt to the LLM and returns the generated text.

        Args:
            prompt:      The formatted prompt string.
            model_name:  Override the default model from settings.
            temperature: Sampling temperature.
            max_tokens:  Maximum tokens to generate.

        Returns:
            The generated summary string, or None on unrecoverable failure.
        """

    @abstractmethod
    async def close_client(self) -> None:
        """Closes the underlying HTTP client connection."""


# ── Groq implementation ───────────────────────────────────────────────────────

class GroqLLMService(BaseLLMService):
    """
    LLM service backed by the Groq Cloud API (AsyncGroq).

    Handles client initialization (singleton), API calls, rate-limit retries
    with parsed Retry-After delays, and exponential back-off for other errors.
    """

    _client = None  # shared singleton across instances

    @classmethod
    def _get_client(cls):
        """Initializes and returns the AsyncGroq client (singleton)."""
        if cls._client is None:
            if not settings.groq_api_key_value:
                raise LLMConnectionError("Groq API key is not configured. Set GROQ_API_KEY in .env.")
            try:
                from groq import AsyncGroq
                logger.info(f"Initializing AsyncGroq client for model '{settings.groq_model_name}'")
                cls._client = AsyncGroq(
                    api_key=settings.groq_api_key_value,
                    timeout=settings.request_timeout,
                    max_retries=0,
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
        max_tokens: int = 2048,
    ) -> Optional[str]:
        from groq import RateLimitError, APIConnectionError, APIStatusError

        client = self._get_client()
        target_model = model_name or settings.groq_model_name
        other_error_retry_count = 0
        current_delay = INITIAL_RETRY_DELAY

        while True:
            try:
                logger.debug(f"[Groq] Sending request to '{target_model}'. Prompt length: {len(prompt)}")
                t0 = time.time()
                response = await client.chat.completions.create(
                    messages=[{"role": "user", "content": prompt}],
                    model=target_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                duration = time.time() - t0

                if response.choices and response.choices[0].message:
                    summary = response.choices[0].message.content
                    usage = response.usage
                    logger.debug(
                        f"[Groq] Response in {duration:.2f}s. "
                        f"Tokens: prompt={usage.prompt_tokens if usage else 'N/A'}, "
                        f"completion={usage.completion_tokens if usage else 'N/A'}."
                    )
                    if summary:
                        return summary.strip()
                    logger.warning(f"[Groq] Model '{target_model}' returned an empty summary.")
                    raise LLMException("LLM returned an empty summary.")
                else:
                    logger.error(f"[Groq] Unexpected response structure: {response}")
                    raise LLMException("Invalid response structure received from Groq.")

            except RateLimitError as e:
                error_body = e.body.get('error', {}) if e.body else {}
                error_message = error_body.get('message', str(e))
                logger.warning(f"[Groq] Rate limit hit: {error_message}")
                wait_time = _parse_retry_after(error_message)
                if wait_time is None:
                    wait_time = DEFAULT_RATE_LIMIT_DELAY
                    logger.info(f"[Groq] No delay parsed. Waiting default {wait_time:.2f}s...")
                else:
                    wait_time += RATE_LIMIT_DELAY_BUFFER
                    logger.info(f"[Groq] Waiting {wait_time:.2f}s (suggested by API)...")
                await asyncio.sleep(wait_time)
                other_error_retry_count = 0
                current_delay = INITIAL_RETRY_DELAY
                continue

            except APIConnectionError:
                logger.warning(
                    f"[Groq] Connection error (attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1})."
                )
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                    logger.error("[Groq] Max retries reached for connection error.")
                    return None
                other_error_retry_count += 1

            except APIStatusError as e:
                if e.status_code >= 500 and other_error_retry_count < MAX_OTHER_ERROR_RETRIES:
                    logger.warning(
                        f"[Groq] Server error {e.status_code} "
                        f"(attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1})."
                    )
                    other_error_retry_count += 1
                else:
                    logger.error(f"[Groq] Non-retryable error {e.status_code}: {e.message}")
                    return None

            except Exception as e:
                logger.warning(
                    f"[Groq] Unexpected error (attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}): {e}",
                    exc_info=True,
                )
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                    logger.error("[Groq] Max retries reached for unexpected error.")
                    return None
                other_error_retry_count += 1

            logger.debug(f"[Groq] Sleeping {current_delay:.2f}s before retry...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RETRY_DELAY)

    async def close_client(self) -> None:
        """Closes the AsyncGroq client connection."""
        if GroqLLMService._client is not None:
            try:
                await GroqLLMService._client.aclose()
                logger.info("[Groq] Closed AsyncGroq client connection.")
                GroqLLMService._client = None
            except Exception as e:
                logger.error(f"[Groq] Error closing client: {e}", exc_info=True)


# ── Gemini implementation ─────────────────────────────────────────────────────
# Import deferred to avoid circular imports at module load time.
from .gemini_key_pool import get_gemini_pool, DEFAULT_RATE_LIMIT_COOLDOWN

class GeminiLLMService(BaseLLMService):
    """
    LLM service backed by Google Gemini via a rotating (api_key × model) pool.

    On 429 ResourceExhausted: marks the current slot and immediately rotates
    to the next available slot — no sleeping while alternatives exist.
    Only sleeps when ALL slots in the pool are in cooldown simultaneously.
    """

    async def generate_summary(
        self,
        prompt: str,
        model_name: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Optional[str]:
        """
        Sends a prompt to Gemini via the key pool and returns the generated text.

        Args:
            prompt:      The formatted prompt string.
            model_name:  Ignored — model is determined by the active pool slot.
            temperature: Sampling temperature.
            max_tokens:  Maximum tokens to generate.

        Returns:
            The generated summary string, or None on unrecoverable failure.
        """
        from google import genai
        from google.genai import errors as genai_errors

        if model_name:
            logger.debug(
                f"[Gemini] model_name='{model_name}' override ignored — "
                f"model is selected by the key pool."
            )

        pool = get_gemini_pool()
        other_error_retry_count = 0
        current_delay = INITIAL_RETRY_DELAY

        while True:

            # ── 1. Get next available slot ──────────────────────────────────
            slot = pool.get_available_slot()

            if slot is None:
                # Every slot is in cooldown — wait for the soonest to recover
                wait_seconds = pool.soonest_available_seconds() + 0.5
                logger.warning(
                    f"[Gemini] All {len(pool)} pool slot(s) are rate-limited. "
                    f"Waiting {wait_seconds:.1f}s for soonest slot to recover..."
                )
                await asyncio.sleep(wait_seconds)
                continue

            # ── 2. Make the API call ──────────────────────────────────────
            try:
                client = slot.get_client()
                logger.debug(
                    f"[Gemini] Request via slot: model='{slot.model_name}', "
                    f"key=…{slot.api_key[-6:]}. Prompt length: {len(prompt)}"
                )

                t0 = time.time()
                response = await client.aio.models.generate_content(
                    model=slot.model_name,
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_tokens,
                    ),
                )
                duration = time.time() - t0

                if response and response.text:
                    logger.debug(
                        f"[Gemini] Response in {duration:.2f}s "
                        f"from '{slot.model_name}' (key=…{slot.api_key[-6:]})."
                    )
                    return response.text.strip()

                # Empty response — soft retry like a server error
                logger.warning(
                    f"[Gemini] Empty response from '{slot.model_name}' "
                    f"(attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1})."
                )
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                    logger.error("[Gemini] Max retries reached for empty response.")
                    return None
                other_error_retry_count += 1
                
                # Skip the exceptions block and go straight to the backoff sleep
                pass

            # ── 3a. Rate limit / API errors (google-genai APIError) ──
            except genai_errors.APIError as e:
                # The google-genai SDK stores HTTP status as .code, not .status_code
                # Use getattr with fallback to handle any SDK version differences
                http_status = getattr(e, "code", None) or getattr(e, "status_code", None)

                if http_status == 429 or "RESOURCE_EXHAUSTED" in str(e).upper():
                    retry_after = _parse_retry_after(str(e)) or DEFAULT_RATE_LIMIT_COOLDOWN
                    slot.mark_rate_limited(retry_after)
                    logger.info(
                        f"[Gemini] Slot '{slot.model_name}' (key=…{slot.api_key[-6:]}) "
                        f"rate-limited (HTTP {http_status}). Rotating to next slot immediately..."
                    )
                    continue  # ← no sleep — immediately try next slot

                if http_status and http_status >= 500:
                    # 5xx server errors — retryable with backoff
                    logger.warning(
                        f"[Gemini] Server error HTTP {http_status} on '{slot.model_name}' "
                        f"(attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}): {e}"
                    )
                    if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                        logger.error("[Gemini] Max retries reached for server error.")
                        return None
                    other_error_retry_count += 1
                else:
                    # 4xx non-retryable (bad key, bad request, etc.)
                    logger.error(
                        f"[Gemini] Non-retryable error HTTP {http_status} "
                        f"on '{slot.model_name}' (key=…{slot.api_key[-6:]}): {e}"
                    )
                    return None


            # ── 3b. Fallback catch for ResourceExhausted from google.api_core ──
            except Exception as e:
                type_name = type(e).__name__
                if "ResourceExhausted" in type_name or "429" in str(e):
                    retry_after = _parse_retry_after(str(e)) or DEFAULT_RATE_LIMIT_COOLDOWN
                    slot.mark_rate_limited(retry_after)
                    logger.info(
                        f"[Gemini] Slot '{slot.model_name}' rate-limited (fallback catch). "
                        f"Rotating immediately..."
                    )
                    continue  # no sleep

                logger.warning(
                    f"[Gemini] Error on '{slot.model_name}' "
                    f"(attempt {other_error_retry_count + 1}/{MAX_OTHER_ERROR_RETRIES + 1}): "
                    f"{type_name}: {e}"
                )
                if other_error_retry_count >= MAX_OTHER_ERROR_RETRIES:
                    logger.error("[Gemini] Max retries reached. Giving up on this request.")
                    return None
                other_error_retry_count += 1

            logger.debug(f"[Gemini] Sleeping {current_delay:.2f}s before retry...")
            await asyncio.sleep(current_delay)
            current_delay = min(current_delay * 2, MAX_RETRY_DELAY)

    async def close_client(self) -> None:
        """
        Resets the key pool singleton so it will be rebuilt from settings on
        the next request. Useful after credential rotation.
        """
        from . import gemini_key_pool as _pool_module
        _pool_module._pool_instance = None
        logger.info("[Gemini] Key pool singleton cleared.")


# ── Factory ───────────────────────────────────────────────────────────────────

_PROVIDER_MAP: dict = {
    "groq":   GroqLLMService,
    "gemini": GeminiLLMService,
}


def get_llm_service() -> BaseLLMService:
    """
    Factory function that returns the configured LLM service instance.

    Reads settings.llm_provider ('groq' or 'gemini') and instantiates the
    corresponding service. This is the single entry point for the rest of the
    codebase — no other file needs to know which provider is active.

    Returns:
        An instance of BaseLLMService (either GroqLLMService or GeminiLLMService).

    Raises:
        ValueError: If the configured provider is not recognized.
    """
    provider = settings.llm_provider
    service_class = _PROVIDER_MAP.get(provider)
    if service_class is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Valid options: {list(_PROVIDER_MAP.keys())}"
        )
    logger.info(f"Using LLM provider: '{provider}' ({service_class.__name__})")
    return service_class()