import uuid
from typing import List, Optional, Literal, Tuple
from uuid import UUID
from pydantic import BaseModel, Field, PositiveInt, NonNegativeInt

NodeType = Literal[
    "FOLDER",
    "FILE",
    "CLASS",
    "FUNCTION",
    "NON_FUNCTION_NON_CLASS",
]

EdgeType = Literal[
    "CONTAINS",
    "IS_PART_OF",
    "DEFINED_IN",
    "METHOD_OF",
    "CALLS",
    "IMPORTS",
    "INHERITS_FROM",
    "USES_IMPORT",
    "REFERENCES",
]

AccessModifier = Literal[
    "public",
    "private",
    "protected"
]

class Edge(BaseModel):
    """
    Represents a directed edge in the graph.
    """
    source_id: UUID = Field(description="The ID of the node where the edge originates.")
    target_id: UUID = Field(description="The ID of the node where the edge terminates.")
    type: EdgeType = Field(description="The type of relationship.")
    label: Optional[str] = Field(None, description="Optional label for the edge (e.g., import alias).")

    model_config = {
        "frozen": True, 
    }

class BaseNode(BaseModel):
    """
    Base model for all nodes in the Code Knowledge Graph.
    Includes common metadata fields.
    """
    id: UUID = Field(default_factory=uuid.uuid4, description="Unique identifier for the node.")
    node_type: NodeType = Field(description="The type of the CKG node.")
    name: str = Field(description="Identifier for the node (e.g., directory name, file name, function name).")
    depth: NonNegativeInt = Field(description="Depth level in the CKG hierarchy (root is 0).")
    belongs_to: Optional[UUID] = Field(None, description="ID of the parent node in the structural hierarchy (e.g., Folder for File, File for Function). None for root.")
    edges: List[Edge] = Field(default_factory=list, description="List of outgoing edges originating from this node.")
    summary: Optional[str] = Field(None, description="AI-generated summary of the node's purpose (populated later).")

class FolderNode(BaseNode):
    """Represents a directory in the codebase."""
    node_type: Literal["FOLDER"] = "FOLDER"
    file_path: str = Field(description="Relative path of the directory from the project root.")

class FileNode(BaseNode):
    """Represents a single .py file."""
    node_type: Literal["FILE"] = "FILE"
    file_path: str = Field(description="Relative path of the file from the project root.")
    module_path: Optional[str] = Field(None, description="Python import path (e.g., my_package.utils.helpers).")

class CodeNode(BaseNode):
    """
    Abstract base model for nodes representing code constructs
    (Functions, Classes, Top-Level Code).
    """
    file_path: str = Field(description="Relative path of the file containing this code.")
    start_line: Optional[PositiveInt] = Field(None, description="Starting line number of the code block (1-based).")
    end_line: Optional[PositiveInt] = Field(None, description="Ending line number of the code block (1-based).")
    docstring: Optional[str] = Field(None, description="Extracted docstring, if any.")
    imports_used: List[str] = Field(default_factory=list, description="Specific imports referenced within this code block's scope.")

class FunctionNode(CodeNode):
    """Represents a function or a method."""
    node_type: Literal["FUNCTION"] = "FUNCTION"
    signature: Optional[str] = Field(None, description="Function signature (e.g., 'def my_func(a: int, b: str = 'default') -> bool').")
    is_method: bool = Field(default=False, description="True if this function is a method of a class.")
    access_modifier: Optional[AccessModifier] = Field(None, description="Inferred access level ('public', 'protected', 'private') based on name.")
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the top-level code.")
    
class ClassNode(CodeNode):
    """Represents a class definition."""
    node_type: Literal["CLASS"] = "CLASS"
    signature: Optional[str] = Field(None, description="Class signature, including constructor (__init__) and parent classes.")
    access_modifier: Optional[AccessModifier] = Field(None, description="Inferred access level ('public', 'protected', 'private') based on name.")
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the top-level code.")

class NonFunctionNonClassNode(CodeNode):
    """Represents top-level code blocks outside functions or classes."""
    node_type: Literal["NON_FUNCTION_NON_CLASS"] = "NON_FUNCTION_NON_CLASS"
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the top-level code.")