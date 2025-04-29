import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware 
from .config import settings
from .api.routes import documentation as documentation_router
from .models.responses import ErrorResponse, ValidationErrorDetail

log_level_str = settings.log_level
numeric_level = getattr(logging, log_level_str.upper(), logging.INFO)
logging.basicConfig(level=numeric_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AutoDoc AI",
    description="AI-powered documentation generation for Python codebases.",
    version="0.1.0",
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handles Pydantic validation errors globally."""
    logger.error(f"Validation error for request {request.url}: {exc.errors()}")
    error_details = [
        ValidationErrorDetail(loc=list(err['loc']), msg=err['msg'], type=err['type']).model_dump()
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            status="error",
            message="Input validation failed.",
            error_details=error_details
        ).model_dump(exclude_none=True) 
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Handles any unexpected exceptions not caught elsewhere."""
    logger.critical(f"Unhandled exception for request {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            status="error",
            message="An unexpected internal server error occurred.",
            error_details=f"{type(exc).__name__}: {exc}" 
        ).model_dump(exclude_none=True)
    )

app.include_router(
    documentation_router.router,
    prefix="/api/v1", 
    tags=["Documentation"] 
)

@app.get("/health", tags=["Health"], status_code=status.HTTP_200_OK)
async def health_check():
    """
    Simple health check endpoint to verify the server is running.
    """
    logger.info("Health check endpoint called.")
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event():
    """
    Actions to perform when the application starts.
    e.g., Initialize database connections, load ML models.
    """
    logger.info("Application starting up...")
    logger.info("Application startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    """
    Actions to perform when the application shuts down.
    e.g., Close database connections, clean up resources.
    """
    logger.info("Application shutting down...")
    logger.info("Application shutdown complete.")