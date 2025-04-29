from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List, Literal, Union

class BaseResponse(BaseModel):
    """Base model for API responses."""
    status: Literal["success", "error"] = Field(description="Indicates if the operation was successful.")
    message: Optional[str] = Field(None, description="An optional message providing context.")

class SuccessResponse(BaseResponse):
    """Response model for successful documentation generation."""
    status: Literal["success"] = "success"
    documentation: str = Field(description="The generated Markdown documentation content.")

class ErrorResponse(BaseResponse):
    """Response model for errors during processing."""
    status: Literal["error"] = "error"
    message: str = Field(description="Description of the error that occurred.")
    error_details: Optional[Union[List[Dict[str, Any]], Dict[str, Any], str]] = Field(
        None,
        description="Optional detailed information about the error (e.g., validation errors, stack trace snippet in dev)."
    )

class ValidationErrorDetail(BaseModel):
    loc: List[str] = Field(description="Location of the error (e.g., ['body', 'field_name']).")
    msg: str = Field(description="Error message.")
    type: str = Field(description="Type of the error.")

class ValidationErrorResponse(ErrorResponse):
    """Specific error response for validation errors."""
    message: str = "Input validation failed."
    error_details: List[ValidationErrorDetail] = Field(description="List of validation errors.")


# You can also define a Union for documentation endpoint responses if preferred
# from typing import Union
# DocumentationResponse = Union[SuccessResponse, ErrorResponse, ValidationErrorResponse]