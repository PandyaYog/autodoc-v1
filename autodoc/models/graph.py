import uuid
from typing import List, Optional, Literal, Tuple, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, PositiveInt, NonNegativeInt

NodeType = Literal[
    "FOLDER",
    "FILE",
    "CLASS",
    "FUNCTION",
    "IMPORT_BLOCK",
    "NON_FUNCTION_NON_CLASS",
    "REACT_COMPONENT",
    "REACT_HOOK",
    # Non-Python config / documentation file nodes
    "MARKDOWN_FILE",
    "TEXT_FILE",
    "YAML_FILE",
    "TOML_FILE",
    "DOCKERFILE",
    # Web asset / data file nodes
    "JSON_FILE",
    "HTML_FILE",
    "CSS_FILE",
]

NON_PYTHON_NODE_TYPES: set = {
    "MARKDOWN_FILE", "TEXT_FILE", "YAML_FILE", "TOML_FILE", "DOCKERFILE",
    "JSON_FILE", "HTML_FILE", "CSS_FILE",
}

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
    "RENDERS",
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
    """Represents a single source code file."""
    node_type: Literal["FILE"] = "FILE"
    file_path: str = Field(description="Relative path of the file from the project root.")
    language: str = Field(description="Programming language of the file (e.g., 'python', 'javascript', 'typescript').")
    module_path: Optional[str] = Field(None, description="Python/JS import path (e.g., my_package.utils.helpers or @/components/Button).")

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

class ImportBlockNode(BaseNode): 
    """Represents a block of top-level import statements in a file."""
    node_type: Literal["IMPORT_BLOCK"] = "IMPORT_BLOCK"
    file_path: str = Field(description="Relative path of the file containing this import block.")
    belongs_to: UUID = Field(description="ID of the parent File node.")
    imports: List[Dict[str, Any]] = Field(default_factory=list, description="List of import statement details.")
    start_line: Optional[PositiveInt] = Field(None, description="Starting line number of the first import (1-based).")
    end_line: Optional[PositiveInt] = Field(None, description="Ending line number of the last import (1-based).")

class NonFunctionNonClassNode(CodeNode):
    """Represents top-level code blocks outside functions, classes or import blocks."""
    node_type: Literal["NON_FUNCTION_NON_CLASS"] = "NON_FUNCTION_NON_CLASS"
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the top-level code.")


class ReactComponentNode(CodeNode):
    """Represents a React functional or class component."""
    node_type: Literal["REACT_COMPONENT"] = "REACT_COMPONENT"
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the component code.")
    props: List[str] = Field(default_factory=list, description="List of props passed to the component")
    hooks_used: List[str] = Field(default_factory=list, description="Hooks like useState, useEffect")
    renders_components: List[str] = Field(default_factory=list, description="Other components rendered in the JSX")


class ReactHookNode(CodeNode):
    """Represents a custom React hook."""
    node_type: Literal["REACT_HOOK"] = "REACT_HOOK"
    signature: Optional[str] = Field(None, description="Hook signature (parameters and return type)")
    code_snippet: Optional[str] = Field(None, description="A representative snippet or summary of the hook code.")


# ---------------------------------------------------------------------------
# Non-Python file nodes (Option A — structural only, no cross-file edges)
# ---------------------------------------------------------------------------

MAX_RAW_CONTENT_LENGTH: int = 6000  # chars; large files are truncated before LLM


class NonPythonFileNode(BaseNode):
    """Base model for non-Python config/documentation files (.md, .txt, .yaml, .toml, Dockerfile)."""
    file_path: str = Field(description="Relative path of the file from the project root.")
    raw_content: Optional[str] = Field(
        None,
        description="Raw file content (may be truncated for large files). Sent to the LLM for summarization."
    )


class MarkdownFileNode(NonPythonFileNode):
    """Represents a Markdown documentation file (.md, .rst)."""
    node_type: Literal["MARKDOWN_FILE"] = "MARKDOWN_FILE"


class TextFileNode(NonPythonFileNode):
    """Represents a plain-text file (.txt)."""
    node_type: Literal["TEXT_FILE"] = "TEXT_FILE"


class YamlFileNode(NonPythonFileNode):
    """Represents a YAML configuration file (.yaml, .yml)."""
    node_type: Literal["YAML_FILE"] = "YAML_FILE"


class TomlFileNode(NonPythonFileNode):
    """Represents a TOML configuration file (.toml)."""
    node_type: Literal["TOML_FILE"] = "TOML_FILE"


class DockerfileNode(NonPythonFileNode):
    """Represents a Dockerfile (exact filename match, no extension)."""
    node_type: Literal["DOCKERFILE"] = "DOCKERFILE"


class JsonFileNode(NonPythonFileNode):
    """Represents a JSON data or configuration file (.json)."""
    node_type: Literal["JSON_FILE"] = "JSON_FILE"


class HtmlFileNode(NonPythonFileNode):
    """Represents an HTML template or page file (.html, .htm)."""
    node_type: Literal["HTML_FILE"] = "HTML_FILE"


class CssFileNode(NonPythonFileNode):
    """Represents a CSS stylesheet file (.css)."""
    node_type: Literal["CSS_FILE"] = "CSS_FILE"