from pydantic import BaseModel, Field
from typing import Optional, List

# NOTE: The primary input (the .zip file) will be handled using
# FastAPI's UploadFile, likely declared directly in the endpoint
# function signature using File(...) or Form(...), not within this model.

# This model serves as a placeholder for potential future request options.
class DocumentationRequestOptions(BaseModel):
    """
    Optional configuration parameters for the documentation generation request.
    (Currently unused, but provides structure for future extension).
    """
    # Example future options:
    # documentation_style: Optional[str] = Field(None, description="Style guide to follow (e.g., 'google', 'numpy').")
    # exclude_paths: Optional[List[str]] = Field(None, description="List of glob patterns to exclude beyond defaults.")
    pass

# If you were to send options as JSON along with the file (less common for simple uploads):
# class DocumentationRequest(BaseModel):
#     options: Optional[DocumentationRequestOptions] = None