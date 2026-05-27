from pydantic import BaseModel, Field
from typing import Optional, Any, Dict, List, Literal, Union
from datetime import datetime


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
        description="Optional detailed information about the error."
    )

class ValidationErrorDetail(BaseModel):
    loc: List[str] = Field(description="Location of the error (e.g., ['body', 'field_name']).")
    msg: str = Field(description="Error message.")
    type: str = Field(description="Type of the error.")

class ValidationErrorResponse(ErrorResponse):
    """Specific error response for validation errors."""
    message: str = "Input validation failed."
    error_details: List[ValidationErrorDetail] = Field(description="List of validation errors.")


class TaskAcceptedResponse(BaseModel):
    """Response returned immediately when a documentation task is accepted (HTTP 202)."""
    task_id: str = Field(description="Unique ID to poll for task status and result.")
    status: str = Field(default="pending", description="Initial task status.")
    message: str = Field(description="Human-readable confirmation message.")


class TaskStatusResponse(BaseModel):
    """
    Response for GET /status/{task_id}.

    Fields are populated based on the current task state:
      - pending/processing : task_id, status, filename, created_at, updated_at
      - completed          : + download_url (ready to fetch the PDF)
      - failed             : + error
    """
    task_id: str = Field(description="The task identifier.")
    status: str = Field(description="Current state: pending | processing | completed | failed.")
    filename: Optional[str] = Field(None, description="Original uploaded filename.")
    download_url: Optional[str] = Field(
        None,
        description="PDF download URL. Present only when status='completed'.",
    )
    error: Optional[str] = Field(
        None,
        description="Human-readable error reason. Present only when status='failed'.",
    )
    markdown: Optional[str] = Field(
        None,
        description="The raw Markdown documentation string. Present only when status='completed'.",
    )
    created_at: Optional[datetime] = Field(None, description="UTC timestamp when the task was created.")
    updated_at: Optional[datetime] = Field(None, description="UTC timestamp of the last status change.")