import logging
from functools import lru_cache
from .models.settings import Settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@lru_cache() 
def get_settings() -> Settings:
    """
    Loads and returns the application settings.

    Uses lru_cache to ensure the Settings object is created only once (singleton pattern).
    Handles potential errors during settings loading.
    """
    try:
        settings = Settings()
        logger.info(f"Loaded settings. Log Level: {settings.log_level}, Groq Model: {settings.groq_model_name}")
        return settings
    except Exception as e:
        logger.critical(f"Fatal error loading application settings: {e}", exc_info=True)
        raise 

settings: Settings = get_settings()