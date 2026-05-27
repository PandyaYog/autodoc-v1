"""
Gemini Key Pool — manages a pool of (api_key × model) slots for the Gemini LLM.

Each slot is one combination of an API key and a model name. When a slot hits
its rate limit (429 / ResourceExhausted), it is marked as cooling down and the
pool immediately moves to the next available slot — no sleeping while other
slots are still free.

Slot layout example (3 keys × 2 models = 6 slots):
    Slot 0:  key1 + gemini-2.5-flash
    Slot 1:  key1 + gemini-2.5-flash-lite
    Slot 2:  key2 + gemini-2.5-flash
    Slot 3:  key2 + gemini-2.5-flash-lite
    Slot 4:  key3 + gemini-2.5-flash
    Slot 5:  key3 + gemini-2.5-flash-lite

The pool is a module-level singleton built once from settings at import time.

SDK note:
    Uses the newer `google-genai` SDK (google.genai.Client) instead of the
    legacy `google.generativeai` which has a global configure() — unsuitable
    for multiple API keys in the same process.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Any

logger = logging.getLogger(__name__)

# Default retry-after delay when the API doesn't tell us how long to wait
DEFAULT_RATE_LIMIT_COOLDOWN: float = 60.0  # seconds


@dataclass
class KeyModelSlot:
    """
    One (api_key, model_name) combination.

    Attributes:
        api_key:             Gemini API key for this slot.
        model_name:          Gemini model identifier (e.g. 'gemini-2.5-flash').
        rate_limited_until:  UTC datetime when this slot becomes usable again,
                             or None if it is currently available.
        _client:             Lazily-initialised google.genai.Client instance.
                             Never access directly — use get_client().
    """
    api_key: str
    model_name: str
    rate_limited_until: Optional[datetime] = field(default=None)
    _client: Optional[Any] = field(default=None, repr=False, compare=False)

    # ── Client access ─────────────────────────────────────────────────────────

    def get_client(self) -> Any:
        """
        Returns a google.genai.Client bound to this slot's API key.
        The client is created lazily on the first call and cached.
        """
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                logger.debug(
                    f"[KeyPool] Initialised genai.Client for model '{self.model_name}' "
                    f"(key …{self.api_key[-6:]})"
                )
            except ImportError:
                raise RuntimeError(
                    "google-genai package is not installed. "
                    "Run: pip install google-genai"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialise Gemini client for model '{self.model_name}': {e}"
                )
        return self._client

    # ── Availability ──────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Returns True if this slot is not currently rate-limited."""
        if self.rate_limited_until is None:
            return True
        return datetime.now(timezone.utc) >= self.rate_limited_until

    def seconds_until_available(self) -> float:
        """
        Returns how many seconds remain until this slot is available.
        Returns 0.0 if the slot is already available.
        """
        if self.rate_limited_until is None:
            return 0.0
        remaining = (self.rate_limited_until - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)

    def mark_rate_limited(self, retry_after_seconds: float) -> None:
        """
        Marks this slot as unavailable for `retry_after_seconds` seconds.

        Args:
            retry_after_seconds: Cooldown duration parsed from the API error,
                                 or DEFAULT_RATE_LIMIT_COOLDOWN as a fallback.
        """
        self.rate_limited_until = datetime.now(timezone.utc) + timedelta(
            seconds=retry_after_seconds
        )
        logger.warning(
            f"[KeyPool] Slot '{self.model_name}' (key …{self.api_key[-6:]}) "
            f"rate-limited for {retry_after_seconds:.0f}s "
            f"(until {self.rate_limited_until.strftime('%H:%M:%S')} UTC)."
        )

    def reset(self) -> None:
        """Clears any active rate-limit cooldown on this slot."""
        self.rate_limited_until = None

    def __str__(self) -> str:
        status = "available" if self.is_available() else f"limited ({self.seconds_until_available():.0f}s)"
        return f"Slot({self.model_name}, key=…{self.api_key[-6:]}, {status})"


class GeminiKeyPool:
    """
    Manages all (api_key × model) slots and exposes a simple interface for
    obtaining an available slot or waiting until one becomes free.

    Usage:
        slot = pool.get_available_slot()
        if slot is None:
            wait = pool.soonest_available_seconds()
            await asyncio.sleep(wait)
            slot = pool.get_available_slot()

        try:
            client = slot.get_client()
            # ... make API call ...
        except ResourceExhausted:
            slot.mark_rate_limited(retry_after)
    """

    def __init__(self, api_keys: List[str], models: List[str]) -> None:
        """
        Builds the slot pool from a list of API keys and a list of models.

        Slots are ordered key-first (all models for key1, then all models for
        key2, etc.) so that when one model on a key hits a limit, the next slot
        tries a different model on the same key before moving to a new key.

        Args:
            api_keys: List of Gemini API keys (one per Google account).
            models:   List of Gemini model names to use with each key.

        Raises:
            ValueError: If no API keys or no models are provided.
        """
        if not api_keys:
            raise ValueError(
                "GeminiKeyPool requires at least one API key. "
                "Set GEMINI_API_KEYS in your .env file."
            )
        if not models:
            raise ValueError(
                "GeminiKeyPool requires at least one model. "
                "Set GEMINI_MODELS in your .env file."
            )

        self._slots: List[KeyModelSlot] = [
            KeyModelSlot(api_key=key, model_name=model)
            for key in api_keys
            for model in models
        ]

        logger.info(
            f"[KeyPool] Initialised pool: "
            f"{len(api_keys)} key(s) × {len(models)} model(s) = {len(self._slots)} slot(s)."
        )
        for i, slot in enumerate(self._slots):
            logger.debug(f"[KeyPool]  Slot {i}: {slot.model_name}, key=…{slot.api_key[-6:]}")

    # ── Slot selection ────────────────────────────────────────────────────────

    def get_available_slot(self) -> Optional[KeyModelSlot]:
        """
        Returns the first slot that is not currently rate-limited, or None
        if all slots are in cooldown.

        The scan starts from index 0 every call so that recovered slots are
        preferred over newly tried ones, reducing unnecessary model switching.
        """
        for slot in self._slots:
            if slot.is_available():
                return slot
        return None

    def soonest_available_seconds(self) -> float:
        """
        Returns how many seconds until the soonest slot becomes available.
        Returns 0.0 if any slot is already available (shouldn't happen if
        called right after get_available_slot() returns None, but safe).
        """
        if not self._slots:
            return DEFAULT_RATE_LIMIT_COOLDOWN

        waits = [slot.seconds_until_available() for slot in self._slots]
        return min(waits)

    def reset_all(self) -> None:
        """Clears all cooldowns (useful for testing or manual recovery)."""
        for slot in self._slots:
            slot.reset()
        logger.info("[KeyPool] All slot cooldowns cleared.")

    # ── Introspection ─────────────────────────────────────────────────────────

    def status_summary(self) -> str:
        """Returns a human-readable summary of all slot states."""
        lines = [f"[KeyPool] {len(self._slots)} slots:"]
        for i, slot in enumerate(self._slots):
            lines.append(f"  [{i}] {slot}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._slots)

    def __repr__(self) -> str:
        available = sum(1 for s in self._slots if s.is_available())
        return f"GeminiKeyPool(total={len(self._slots)}, available={available})"


# ── Module-level singleton ────────────────────────────────────────────────────
# Built lazily on first import that accesses `gemini_pool`.
# This avoids circular imports and allows settings to load first.

_pool_instance: Optional[GeminiKeyPool] = None


def get_gemini_pool() -> GeminiKeyPool:
    """
    Returns the shared GeminiKeyPool singleton, creating it on first call.

    Reads api_keys and models from the effective_gemini_* properties on
    settings so that both the new multi-key fields and the legacy single-key
    fields are respected.

    Returns:
        GeminiKeyPool singleton.

    Raises:
        ValueError: If no API keys or models are configured.
    """
    global _pool_instance
    if _pool_instance is None:
        from ..config import settings
        api_keys = settings.effective_gemini_api_keys
        models = settings.effective_gemini_models
        _pool_instance = GeminiKeyPool(api_keys=api_keys, models=models)
    return _pool_instance
