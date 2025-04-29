import logging
from typing import Optional, Literal
from pydantic import Field, SecretStr, ByteSize, PositiveInt
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

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

    groq_api_key: SecretStr = Field(
        description="API key for Groq Cloud."
    )
    groq_model_name: str = Field(
        default="llama3-8b-8192",
        description="The specific Groq model to use for generation."
    )
    request_timeout: PositiveInt = Field(
        default=6000,
        description="Timeout in seconds for requests to the Groq API."
    )

    temp_dir_base: Optional[str] = Field(
        default=None,
        description="Optional base directory for creating temporary extraction folders. If None, system default is used."
    )

    model_config = SettingsConfigDict(
        env_file='.env',         
        env_file_encoding='utf-8',
        case_sensitive=False,     
        extra='ignore'            
    )

    @property
    def groq_api_key_value(self) -> str:
        """Helper property to easily access the unwrapped API key."""
        return self.groq_api_key.get_secret_value()
