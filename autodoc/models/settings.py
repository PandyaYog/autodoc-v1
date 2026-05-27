import logging
from typing import Optional, Literal, List
from pydantic import Field, SecretStr, ByteSize, PositiveInt, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LLMProvider = Literal["groq", "gemini"]


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables or .env file.
    """

    log_level: LogLevel = Field(
        default="INFO",
        description="Logging level for the application."
    )

    max_zip_size: ByteSize = Field(
        default=ByteSize("50000000000"),
        description="Maximum allowed size for uploaded ZIP files."
    )

    # ── LLM provider selection ────────────────────────────────────────────────
    llm_provider: LLMProvider = Field(
        default="groq",
        description="Which LLM backend to use: 'groq' or 'gemini'."
    )

    # ── Groq settings ─────────────────────────────────────────────────────────
    groq_api_key: Optional[SecretStr] = Field(
        default=None,
        description="API key for Groq Cloud. Required when llm_provider='groq'."
    )
    groq_model_name: str = Field(
        default="llama-3.3-70b-versatile",
        description="The Groq model to use for generation."
    )

    # ── Gemini settings (multi-key pool) ──────────────────────────────────────
    #
    # Set GEMINI_API_KEYS as a comma-separated list of API keys (one per
    # Google account). Set GEMINI_MODELS as a comma-separated list of models
    # to try. The pool will create one slot for every (key × model) combination.
    #
    # Example .env:
    #   GEMINI_API_KEYS=AIzaSy...,AIzaSy...,AIzaSy...
    #   GEMINI_MODELS=gemini-2.5-flash,gemini-2.5-flash-lite,gemini-3.1-flash-lite
    #
    # Backward-compat: if you only have a single key, you can still set
    # GEMINI_API_KEY (singular). It will be merged into the pool automatically.
    gemini_api_keys: List[str] = Field(
        default_factory=list,
        description="Comma-separated Gemini API keys (one per Google account)."
    )
    gemini_models: List[str] = Field(
        default_factory=list,
        description="Comma-separated Gemini model names to use in the key pool."
    )

    # Legacy single-key fields — kept for backward compatibility.
    # If set, the key/model are merged into gemini_api_keys/gemini_models.
    gemini_api_key: Optional[SecretStr] = Field(
        default=None,
        description="[Deprecated] Single Gemini API key. Use GEMINI_API_KEYS instead."
    )
    gemini_model_name: str = Field(
        default="gemini-2.5-flash",
        description="[Deprecated] Single Gemini model. Use GEMINI_MODELS instead."
    )

    # ── Shared settings ───────────────────────────────────────────────────────
    request_timeout: PositiveInt = Field(
        default=6000,
        description="Timeout in seconds for requests to the LLM API."
    )

    temp_dir_base: Optional[str] = Field(
        default=None,
        description="Optional base directory for temporary extraction folders. None = system default."
    )

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("gemini_api_keys", mode="before")
    @classmethod
    def parse_gemini_api_keys(cls, v) -> List[str]:
        """Accepts either a comma-separated string or a list. Strips whitespace."""
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        if isinstance(v, list):
            return [str(k).strip() for k in v if str(k).strip()]
        return []

    @field_validator("gemini_models", mode="before")
    @classmethod
    def parse_gemini_models(cls, v) -> List[str]:
        """Accepts either a comma-separated string or a list. Strips whitespace."""
        if isinstance(v, str):
            return [m.strip() for m in v.split(",") if m.strip()]
        if isinstance(v, list):
            return [str(m).strip() for m in v if str(m).strip()]
        return []

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def groq_api_key_value(self) -> Optional[str]:
        """Returns the unwrapped Groq API key, or None if not set."""
        return self.groq_api_key.get_secret_value() if self.groq_api_key else None

    @property
    def gemini_api_key_value(self) -> Optional[str]:
        """[Deprecated] Returns the single legacy Gemini API key value."""
        return self.gemini_api_key.get_secret_value() if self.gemini_api_key else None

    @property
    def effective_gemini_api_keys(self) -> List[str]:
        """
        Returns the full list of Gemini API keys to use in the pool.

        Merges gemini_api_keys (multi-key list) with the legacy gemini_api_key
        (single key) for backward compatibility. Duplicates are removed while
        preserving order.
        """
        keys: List[str] = list(self.gemini_api_keys)
        legacy = self.gemini_api_key_value
        if legacy and legacy not in keys:
            keys.append(legacy)
        return keys

    @property
    def effective_gemini_models(self) -> List[str]:
        """
        Returns the full list of Gemini models to use in the pool.

        Falls back to the legacy gemini_model_name if no models are configured.
        """
        if self.gemini_models:
            return self.gemini_models
        return [self.gemini_model_name]
