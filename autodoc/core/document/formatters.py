import logging
from typing import Optional, Union
from ...models.graph import (
    BaseNode,
    FolderNode,
    FileNode,
    ClassNode,
    FunctionNode,
    NonFunctionNonClassNode
)

logger = logging.getLogger(__name__)

def _create_heading(text: str, level: int) -> str:
    """Creates a Markdown heading."""
    if not text:
        return ""
    level = max(1, min(6, level)) 
    return f"{'#' * level} {text}\n\n"

def _create_code_block(code: Optional[str], lang: str = 'python') -> str:
    """Creates a Markdown fenced code block."""
    if not code:
        return ""
    code = code.replace('```', '\\`\\`\\`')
    return f"```python\n{code.strip()}\n```\n\n"

def _format_docstring(docstring: Optional[str]) -> str:
    """Formats a docstring, potentially as a blockquote."""
    if not docstring:
        return ""
    quoted_lines = [f"> {line}" for line in docstring.strip().splitlines()]
    return "\n".join(quoted_lines) + "\n\n"
    # Alternative: Just return the docstring as preformatted text or plain text
    # return f"**Docstring:**\n\n{docstring}\n\n"

def _format_summary(summary: Optional[str]) -> str:
    """Formats the AI summary."""
    if not summary:
        return "**Summary:** (Not available)\n\n"
    return f"**Summary:**\n\n{summary.strip()}\n\n"

def _format_metadata_line(key: str, value: Optional[str]) -> str:
    """Formats a simple key-value metadata line."""
    if value is None or value == "":
        return ""
    return f"- **{key}:** `{value}`\n"

def format_folder_markdown(node: FolderNode, heading_level: int = 2) -> str:
    """Formats a FolderNode into Markdown."""
    logger.debug(f"Formatting FolderNode: {node.name}")
    md = _create_heading(f"Folder: {node.name}", heading_level)
    md += _format_metadata_line("Path", node.file_path)
    md += _format_summary(node.summary)
    return md

def format_file_markdown(node: FileNode, heading_level: int = 3) -> str:
    """Formats a FileNode into Markdown."""
    logger.debug(f"Formatting FileNode: {node.name}")
    md = _create_heading(f"File: {node.file_path}", heading_level)
    md += _format_metadata_line("Module Path", node.module_path)
    md += _format_summary(node.summary)
    return md

def format_class_markdown(node: ClassNode, heading_level: int = 4) -> str:
    """Formats a ClassNode into Markdown."""
    logger.debug(f"Formatting ClassNode: {node.name}")
    md = _create_heading(f"Class: {node.name}", heading_level)
    md += _format_metadata_line("Access", node.access_modifier)
    # TODO: Add inheritance info if available from resolver
    # inheritance_info = get_inheritance_info(ckg, node.id) # Assembler might handle this
    # md += _format_metadata_line("Inherits From", inheritance_info)

    if node.signature:
        md += f"**Signature:**\n{_create_code_block(node.signature)}"
    # Decide whether to include docstring if summary exists
    # if node.docstring:
    #     md += _format_docstring(node.docstring)
    md += _format_summary(node.summary)
    if node.code_snippet:
        md += "<details>\n"
        md += f"<summary>Code Snippet (Lines {node.start_line}-{node.end_line})</summary>\n\n"
        md += _create_code_block(node.code_snippet)
        md += "</details>\n\n"
    return md

def format_function_markdown(node: FunctionNode, heading_level: int = 5) -> str:
    """Formats a FunctionNode (or Method) into Markdown."""
    logger.debug(f"Formatting FunctionNode: {node.name}")
    func_type = "Method" if node.is_method else "Function"
    md = _create_heading(f"{func_type}: {node.name}", heading_level)
    if node.is_method:
        md += _format_metadata_line("Access", node.access_modifier)

    if node.signature:
        md += f"**Signature:**\n{_create_code_block(node.signature)}"
    # Decide whether to include docstring if summary exists
    # if node.docstring:
    #     md += _format_docstring(node.docstring)
    md += _format_summary(node.summary)
    if node.code_snippet:
        md += f"**Code Snippet (Lines {node.start_line}-{node.end_line}):**\n"
        md += _create_code_block(node.code_snippet)
    return md

def format_non_function_non_class_markdown(node: NonFunctionNonClassNode, heading_level: int = 5) -> str:
    """Formats a NonFunctionNonClassNode into Markdown."""
    logger.debug(f"Formatting NonFunctionNonClassNode: {node.name}")
    heading_text = f"Top-Level Code: {node.name}"
    if node.start_line and node.end_line:
        heading_text = f"Top-Level Code (Lines {node.start_line}-{node.end_line})"

    md = _create_heading(heading_text, heading_level)
    md += _format_summary(node.summary)
    if node.code_snippet:
        md += "**Code Snippet:**\n"
        md += _create_code_block(node.code_snippet)
    return md


def format_node_markdown(node: BaseNode, heading_level: int) -> str:
    """
    Dispatches formatting to the appropriate function based on node type.

    Args:
        node: The CKG node object (must be a specific subclass like FileNode).
        heading_level: The desired Markdown heading level (1-6).

    Returns:
        A formatted Markdown string for the node, or an empty string if
        the node type is unrecognized or formatting fails.
    """
    formatter_map = {
        "FOLDER": format_folder_markdown,
        "FILE": format_file_markdown,
        "CLASS": format_class_markdown,
        "FUNCTION": format_function_markdown,
        "NON_FUNCTION_NON_CLASS": format_non_function_non_class_markdown,
    }

    formatter = formatter_map.get(node.node_type)

    if formatter:
        try:
            return formatter(node, heading_level)
        except Exception as e:
            logger.error(f"Error formatting node {node.id} ({node.node_type} '{node.name}'): {e}", exc_info=True)
            return f"_{{Error formatting {node.node_type} node: {node.name}}}_"
    else:
        logger.warning(f"No Markdown formatter found for node type: {node.node_type}")
        return ""