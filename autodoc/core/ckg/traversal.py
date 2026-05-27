import ast
import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any
from uuid import UUID
from .ast_visitor import ASTVisitor
from .graph import CKG
from ...models.graph import (
    FolderNode,
    FileNode,
    ClassNode,
    FunctionNode,
    ImportBlockNode,
    NonFunctionNonClassNode,
    NodeType,
    NonPythonFileNode,
    MarkdownFileNode,
    TextFileNode,
    YamlFileNode,
    TomlFileNode,
    DockerfileNode,
    MAX_RAW_CONTENT_LENGTH,
    ReactComponentNode,
    ReactHookNode,
    JsonFileNode,
    HtmlFileNode,
    CssFileNode,
)
from .react_visitor import ReactVisitor
from .tree_sitter_parser import get_javascript_parser, get_typescript_parser, get_tsx_parser

logger = logging.getLogger(__name__)

# Sentinel placed in raw_content when a non-Python file is empty.
# Imported by summarizer.py to short-circuit LLM calls for such nodes.
EMPTY_FILE_SENTINEL = "[This file is empty — no content to document.]"

# Maps file extensions / exact names to CKG node type strings
_EXT_TO_NODE_TYPE: dict = {
    '.md':   'MARKDOWN_FILE',
    '.rst':  'TEXT_FILE',
    '.txt':  'TEXT_FILE',
    '.yaml': 'YAML_FILE',
    '.yml':  'YAML_FILE',
    '.toml': 'TOML_FILE',
    # Web asset / data file types
    '.json': 'JSON_FILE',
    '.html': 'HTML_FILE',
    '.htm':  'HTML_FILE',
    '.css':  'CSS_FILE',
}
_FILENAME_TO_NODE_TYPE: dict = {
    'dockerfile': 'DOCKERFILE',
}

# Per-type content limits (chars). CSS/HTML are often larger than config files.
# JSON gets smart-truncation below, so its limit is just a hard safety cap.
_NODE_TYPE_CONTENT_LIMITS: dict = {
    'CSS_FILE':  10_000,
    'HTML_FILE': 10_000,
}

_NODE_CLASS_MAP: dict = {
    'MARKDOWN_FILE': MarkdownFileNode,
    'TEXT_FILE':     TextFileNode,
    'YAML_FILE':     YamlFileNode,
    'TOML_FILE':     TomlFileNode,
    'DOCKERFILE':    DockerfileNode,
    # Web asset / data file types
    'JSON_FILE':     JsonFileNode,
    'HTML_FILE':     HtmlFileNode,
    'CSS_FILE':      CssFileNode,
}


def _truncate_json_smart(content: str, filename: str) -> str:
    """
    Produces a LLM-friendly preview of a large JSON file.

    Instead of raw-truncating (which yields broken JSON), this function:
    - Parses the JSON and renders the top-level keys with their value types.
    - Caps output at 30 top-level keys to stay within context limits.
    - Falls back to plain truncation if the content is not valid JSON.

    Args:
        content: The full raw JSON string.
        filename: The file name (used in log messages).

    Returns:
        A structured preview string suitable for sending to the LLM.
    """
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            lines = ["{"]
            items = list(parsed.items())
            preview_items = items[:30]
            for k, v in preview_items:
                value_hint = type(v).__name__
                if isinstance(v, list):
                    value_hint = f"array[{len(v)} items]"
                elif isinstance(v, dict):
                    value_hint = f"object[{len(v)} keys]"
                elif isinstance(v, str) and len(v) < 80:
                    # Show short string values verbatim for config clarity
                    value_hint = f'"{v}"'
                lines.append(f'  "{k}": {value_hint},')
            if len(items) > 30:
                lines.append(f"  ... ({len(items) - 30} more top-level keys)")
            lines.append(f"}}  // {len(content)} total chars — preview only")
            return "\n".join(lines)
        elif isinstance(parsed, list):
            # Top-level array (e.g. eslint overrides, i18n arrays)
            preview = f"[  // array of {len(parsed)} items\n"
            for item in parsed[:5]:
                preview += f"  {json.dumps(item)[:120]},\n"
            if len(parsed) > 5:
                preview += f"  ... ({len(parsed) - 5} more items)\n"
            preview += f"]  // {len(content)} total chars — preview only"
            return preview
        else:
            # Scalar JSON — just truncate safely
            return content[:MAX_RAW_CONTENT_LENGTH] + f"\n\n... (truncated — {len(content)} total chars)"
    except json.JSONDecodeError:
        logger.warning(f"Could not parse '{filename}' as JSON during smart-truncation; falling back to raw truncation.")
        return content[:MAX_RAW_CONTENT_LENGTH] + f"\n\n... (truncated — {len(content)} total chars, invalid JSON?)"


def _determine_non_python_node_type(file_path: Path) -> Optional[str]:
    """Returns the CKG node type string for a non-Python file, or None if unsupported."""
    fname_lower = file_path.name.lower()
    ext_lower = file_path.suffix.lower()
    return _FILENAME_TO_NODE_TYPE.get(fname_lower) or _EXT_TO_NODE_TYPE.get(ext_lower)


def _process_non_python_file(
    ckg: CKG,
    file_path: Path,
    project_root: Path,
    parent_folder_id: UUID,
    current_depth: int,
    node_type: str,
):
    """
    Reads a non-Python file, creates the appropriate CKG node, and adds
    structural edges (CONTAINS / IS_PART_OF) to the parent folder.
    """
    NodeClass = _NODE_CLASS_MAP.get(node_type)
    if not NodeClass:
        logger.warning(f"Unknown non-Python node type '{node_type}' for {file_path}. Skipping.")
        return

    relative_path = file_path.relative_to(project_root)
    raw_content: Optional[str] = None
    # Determine the effective content size limit for this file type
    limit = _NODE_TYPE_CONTENT_LIMITS.get(node_type, MAX_RAW_CONTENT_LENGTH)
    try:
        content = file_path.read_text(encoding='utf-8', errors='replace')
        if not content or not content.strip():
            # Empty file — use a sentinel so the summarizer can short-circuit
            # the LLM call entirely instead of hallucinating placeholder sections.
            raw_content = EMPTY_FILE_SENTINEL
            logger.debug(f"Non-Python file is empty: {file_path.name}")
        elif node_type == 'JSON_FILE' and len(content) > limit:
            # Smart-truncation for JSON: show top-level keys instead of raw-cut bytes
            # so the LLM never receives a syntactically broken JSON fragment.
            raw_content = _truncate_json_smart(content, file_path.name)
        elif len(content) > limit:
            raw_content = (
                content[:limit]
                + f"\n\n... (truncated — {len(content)} total chars)"
            )
        else:
            raw_content = content
    except Exception as e:
        logger.warning(f"Could not read content of non-Python file {file_path}: {e}")

    node = NodeClass(
        name=file_path.name,
        file_path=str(relative_path),
        raw_content=raw_content,
        depth=current_depth,
        belongs_to=parent_folder_id,
    )
    node_id = ckg.add_node(node)
    ckg.add_edge(parent_folder_id, node_id, type="CONTAINS")
    ckg.add_edge(node_id, parent_folder_id, type="IS_PART_OF")
    logger.debug(f"Created {node_type} node: {file_path.name} (depth {current_depth})")


def _calculate_module_path(relative_path: Path) -> Optional[str]:
    """
    Calculates the Python module path from a relative file path.

    Args:
        relative_path: The path relative to the project root.

    Returns:
        The Python module path string (e.g., 'package.subpackage.module'),
        or None if it cannot be determined.
    """
    if not relative_path.name.endswith(".py"):
        return None

    parts = list(relative_path.parts)

    if not parts:
        return None

    if parts[-1] == "__init__.py":
        parts.pop()
        if not parts:
             return ""
    else:
        parts[-1] = relative_path.stem

    if not parts and relative_path.name == "__init__.py":
        return ""

    module_path = ".".join(parts)
    return module_path


def _process_python_file(
    ckg: CKG,
    file_path: Path,
    project_root: Path,
    parent_folder_id: UUID,
    current_depth: int
):
    """
    Processes a single Python file: parses AST, extracts info, adds nodes/edges to CKG.
    """
    logger.debug(f"Processing file: {file_path} at depth {current_depth}")
    relative_path = file_path.relative_to(project_root)
    module_path = _calculate_module_path(relative_path)

    file_node = FileNode(
        name=file_path.name,
        file_path=str(relative_path),
        language="python",
        module_path=module_path,
        depth=current_depth,
        belongs_to=parent_folder_id,
    )
    file_node_id = ckg.add_node(file_node)

    ckg.add_edge(parent_folder_id, file_node_id, type="CONTAINS")
    ckg.add_edge(file_node_id, parent_folder_id, type="IS_PART_OF")

    try:
        source_code = file_path.read_text(encoding='utf-8')
        tree = ast.parse(source_code, filename=str(file_path))
    except FileNotFoundError:
        logger.error(f"File not found during processing: {file_path}")
        return
    except UnicodeDecodeError:
        logger.error(f"Could not decode file {file_path} as UTF-8. Skipping.")
        return
    except SyntaxError as e:
        logger.error(f"Syntax error in file {file_path}, line {e.lineno}: {e.msg}. Skipping AST analysis for this file.")
        return
    except Exception as e:
        logger.error(f"Failed to read or parse file {file_path}: {e}", exc_info=True)
        return

    try:
        visitor = ASTVisitor(str(file_path), source_code)
        visitor.visit(tree)
        results = visitor.get_results()
    except Exception as e:
        logger.error(f"Error visiting AST for file {file_path}: {e}", exc_info=True)
        return

    node_map: Dict[Tuple[NodeType, str, int], UUID] = {}
    file_node_nx = ckg.get_node_nx_data(file_node_id)
    temp_ast_classes = []

    imports_data: List[Dict[str, Any]] = results.get("imports", [])
    if imports_data:
        min_line = min(imp.get("start_line") for imp in imports_data if imp.get("start_line") is not None)
        max_line = max(imp.get("end_line") for imp in imports_data if imp.get("end_line") is not None)

        import_block_node = ImportBlockNode(
            name=f"Imports (L{min_line}-L{max_line})",
            file_path=str(relative_path),
            start_line=min_line,
            end_line=max_line,
            imports=imports_data, 
            depth=current_depth + 1, 
            belongs_to=file_node_id,
        )
        import_block_id = ckg.add_node(import_block_node)
        ckg.add_edge(file_node_id, import_block_id, type="CONTAINS")
        ckg.add_edge(import_block_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(import_block_id, file_node_id, type="IS_PART_OF")
        logger.debug(f"Created ImportBlockNode for {file_path.name}")

    for class_data in results.get("classes", []):
        temp_ast_classes.append(class_data)
        class_node = ClassNode(
            name=class_data["name"],
            file_path=str(relative_path),
            start_line=class_data["start_line"],
            end_line=class_data["end_line"],
            docstring=class_data["docstring"],
            signature=f"class {class_data['name']}({', '.join(class_data.get('bases', []))})",
            access_modifier=class_data["access_modifier"],
            code_snippet=class_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            imports_used=class_data.get("used_names", [])
        )
        class_node_id = ckg.add_node(class_node)
        node_map[("CLASS", class_node.name, class_node.start_line)] = class_node_id
        ckg.add_edge(file_node_id, class_node_id, type="CONTAINS")
        ckg.add_edge(class_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(class_node_id, file_node_id, type="IS_PART_OF")

        for method_data in class_data.get("methods", []):
            method_node = FunctionNode(
                name=method_data["name"],
                file_path=str(relative_path),
                start_line=method_data["start_line"],
                end_line=method_data["end_line"],
                docstring=method_data["docstring"],
                signature=method_data["signature"],
                is_method=True,
                access_modifier=method_data["access_modifier"],
                code_snippet=method_data["code_snippet"],
                depth=current_depth + 2,
                belongs_to=class_node_id,
                imports_used=method_data.get("used_names", [])
            )
            method_node_id = ckg.add_node(method_node)
            node_map[("FUNCTION", method_node.name, method_node.start_line)] = method_node_id
            ckg.add_edge(class_node_id, method_node_id, type="CONTAINS")
            ckg.add_edge(method_node_id, class_node_id, type="METHOD_OF")
            ckg.add_edge(method_node_id, class_node_id, type="IS_PART_OF")

    for func_data in results.get("functions", []):
        func_node = FunctionNode(
            name=func_data["name"],
            file_path=str(relative_path),
            start_line=func_data["start_line"],
            end_line=func_data["end_line"],
            docstring=func_data["docstring"],
            signature=func_data["signature"],
            is_method=False,
            access_modifier=func_data["access_modifier"],
            code_snippet=func_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            imports_used=func_data.get("used_names", [])
        )
        func_node_id = ckg.add_node(func_node)
        node_map[("FUNCTION", func_node.name, func_node.start_line)] = func_node_id
        ckg.add_edge(file_node_id, func_node_id, type="CONTAINS")
        ckg.add_edge(func_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(func_node_id, file_node_id, type="IS_PART_OF")

    for tl_data in results.get("top_level_code", []):
        tl_node = NonFunctionNonClassNode(
            name=tl_data["name"],
            file_path=str(relative_path),
            start_line=tl_data["start_line"],
            end_line=tl_data["end_line"],
            docstring=None,
            code_snippet=tl_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            imports_used=tl_data.get("used_names", [])
        )
        tl_node_id = ckg.add_node(tl_node)
        ckg.add_edge(file_node_id, tl_node_id, type="CONTAINS")
        ckg.add_edge(tl_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(tl_node_id, file_node_id, type="IS_PART_OF")

    if file_node_nx:
        file_node_nx['ast_calls'] = results.get("calls", [])
        file_node_nx['node_map'] = node_map
        file_node_nx['ast_classes'] = temp_ast_classes

    logger.debug(f"Finished processing Python file: {file_path}")

def _process_js_ts_file(
    ckg: CKG,
    file_path: Path,
    project_root: Path,
    parent_folder_id: UUID,
    current_depth: int
):
    """
    Processes a single JS/TS/JSX/TSX file using Tree-sitter.
    """
    logger.debug(f"Processing JS/TS file: {file_path} at depth {current_depth}")
    relative_path = file_path.relative_to(project_root)
    ext = file_path.suffix.lower()
    
    language = "javascript"
    if ext in ('.ts', '.tsx'):
        language = "typescript"

    module_path = str(relative_path.with_suffix('')).replace('/', '.')

    file_node = FileNode(
        name=file_path.name,
        file_path=str(relative_path),
        language=language,
        module_path=module_path,
        depth=current_depth,
        belongs_to=parent_folder_id,
    )
    file_node_id = ckg.add_node(file_node)

    ckg.add_edge(parent_folder_id, file_node_id, type="CONTAINS")
    ckg.add_edge(file_node_id, parent_folder_id, type="IS_PART_OF")

    try:
        source_code_bytes = file_path.read_bytes()
        
        if ext == '.tsx':
            parser = get_tsx_parser()
        elif ext == '.ts':
            parser = get_typescript_parser()
        else:
            parser = get_javascript_parser()
            
        tree = parser.parse(source_code_bytes)
        
        visitor = ReactVisitor(str(file_path), source_code_bytes)
        visitor.visit(tree)
        results = visitor.get_results()
    except Exception as e:
        logger.error(f"Failed to parse or visit JS/TS file {file_path}: {e}", exc_info=True)
        return

    node_map: Dict[Tuple[NodeType, str, int], UUID] = {}
    file_node_nx = ckg.get_node_nx_data(file_node_id)
    temp_ast_classes = []

    imports_data = results.get("imports", [])
    if imports_data:
        min_line = min(imp.get("start_line") for imp in imports_data if imp.get("start_line") is not None)
        max_line = max(imp.get("end_line") for imp in imports_data if imp.get("end_line") is not None)

        import_block_node = ImportBlockNode(
            name=f"Imports (L{min_line}-L{max_line})",
            file_path=str(relative_path),
            start_line=min_line,
            end_line=max_line,
            imports=imports_data, 
            depth=current_depth + 1, 
            belongs_to=file_node_id,
        )
        import_block_id = ckg.add_node(import_block_node)
        ckg.add_edge(file_node_id, import_block_id, type="CONTAINS")
        ckg.add_edge(import_block_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(import_block_id, file_node_id, type="IS_PART_OF")

    for comp_data in results.get("react_components", []):
        comp_node = ReactComponentNode(
            name=comp_data["name"],
            file_path=str(relative_path),
            start_line=comp_data["start_line"],
            end_line=comp_data["end_line"],
            docstring=comp_data.get("docstring"),
            code_snippet=comp_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            props=comp_data.get("props", []),
            hooks_used=comp_data.get("hooks_used", []),
            renders_components=comp_data.get("renders_components", [])
        )
        comp_node_id = ckg.add_node(comp_node)
        node_map[("REACT_COMPONENT", comp_node.name, comp_node.start_line)] = comp_node_id
        ckg.add_edge(file_node_id, comp_node_id, type="CONTAINS")
        ckg.add_edge(comp_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(comp_node_id, file_node_id, type="IS_PART_OF")

    for hook_data in results.get("react_hooks", []):
        hook_node = ReactHookNode(
            name=hook_data["name"],
            file_path=str(relative_path),
            start_line=hook_data["start_line"],
            end_line=hook_data["end_line"],
            docstring=hook_data.get("docstring"),
            signature=hook_data.get("signature"),
            code_snippet=hook_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id
        )
        hook_node_id = ckg.add_node(hook_node)
        node_map[("REACT_HOOK", hook_node.name, hook_node.start_line)] = hook_node_id
        ckg.add_edge(file_node_id, hook_node_id, type="CONTAINS")
        ckg.add_edge(hook_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(hook_node_id, file_node_id, type="IS_PART_OF")

    for class_data in results.get("classes", []):
        temp_ast_classes.append(class_data)
        class_node = ClassNode(
            name=class_data["name"],
            file_path=str(relative_path),
            start_line=class_data["start_line"],
            end_line=class_data["end_line"],
            docstring=class_data.get("docstring"),
            signature=f"class {class_data['name']}",
            access_modifier="public",
            code_snippet=class_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            imports_used=class_data.get("used_names", [])
        )
        class_node_id = ckg.add_node(class_node)
        node_map[("CLASS", class_node.name, class_node.start_line)] = class_node_id
        ckg.add_edge(file_node_id, class_node_id, type="CONTAINS")
        ckg.add_edge(class_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(class_node_id, file_node_id, type="IS_PART_OF")

        for method_data in class_data.get("methods", []):
            method_node = FunctionNode(
                name=method_data["name"],
                file_path=str(relative_path),
                start_line=method_data["start_line"],
                end_line=method_data["end_line"],
                docstring=method_data.get("docstring"),
                signature=method_data["signature"],
                is_method=True,
                access_modifier="public",
                code_snippet=method_data["code_snippet"],
                depth=current_depth + 2,
                belongs_to=class_node_id,
                imports_used=method_data.get("used_names", [])
            )
            method_node_id = ckg.add_node(method_node)
            node_map[("FUNCTION", method_node.name, method_node.start_line)] = method_node_id
            ckg.add_edge(class_node_id, method_node_id, type="CONTAINS")
            ckg.add_edge(method_node_id, class_node_id, type="METHOD_OF")
            ckg.add_edge(method_node_id, class_node_id, type="IS_PART_OF")

    for func_data in results.get("functions", []):
        func_node = FunctionNode(
            name=func_data["name"],
            file_path=str(relative_path),
            start_line=func_data["start_line"],
            end_line=func_data["end_line"],
            docstring=func_data.get("docstring"),
            signature=func_data.get("signature"),
            is_method=False,
            access_modifier="public",
            code_snippet=func_data["code_snippet"],
            depth=current_depth + 1,
            belongs_to=file_node_id,
            imports_used=func_data.get("used_names", [])
        )
        func_node_id = ckg.add_node(func_node)
        node_map[("FUNCTION", func_node.name, func_node.start_line)] = func_node_id
        ckg.add_edge(file_node_id, func_node_id, type="CONTAINS")
        ckg.add_edge(func_node_id, file_node_id, type="DEFINED_IN")
        ckg.add_edge(func_node_id, file_node_id, type="IS_PART_OF")

    if file_node_nx:
        file_node_nx['ast_calls'] = results.get("calls", [])
        file_node_nx['node_map'] = node_map
        file_node_nx['ast_classes'] = temp_ast_classes

    logger.debug(f"Finished processing JS/TS file: {file_path}")


def _traverse_directory(
    ckg: CKG,
    current_path: Path,
    project_root: Path,
    parent_node_id: Optional[UUID],
    current_depth: int,
    root_name: Optional[str] = None
):
    """
    Recursively traverses directories using DFS, processing files and subdirectories.
    Uses root_name for the top-level folder node if provided.
    """
    if not current_path.is_dir():
        logger.warning(f"Traversal path is not a directory: {current_path}. Skipping.")
        return

    logger.debug(f"Traversing directory: {current_path} at depth {current_depth}")
    relative_path = current_path.relative_to(project_root)

    node_name = root_name if current_depth == 0 and root_name else current_path.name

    folder_node = FolderNode(
        name=node_name,
        file_path=str(relative_path),
        depth=current_depth,
        belongs_to=parent_node_id,
    )
    folder_node_id = ckg.add_node(folder_node)

    if parent_node_id:
        ckg.add_edge(parent_node_id, folder_node_id, type="CONTAINS")
        ckg.add_edge(folder_node_id, parent_node_id, type="IS_PART_OF")

    try:
        files = []
        dirs = []
        for item in current_path.iterdir():
            if item.is_dir():
                dirs.append(item)
            elif item.is_file():
                files.append(item)

        files.sort()
        dirs.sort()

        for file_item in files:
            if file_item.name.lower().endswith(".py"):
                _process_python_file(
                    ckg=ckg,
                    file_path=file_item,
                    project_root=project_root,
                    parent_folder_id=folder_node_id,
                    current_depth=current_depth + 1
                )
            elif file_item.suffix.lower() in {'.js', '.jsx', '.ts', '.tsx'}:
                _process_js_ts_file(
                    ckg=ckg,
                    file_path=file_item,
                    project_root=project_root,
                    parent_folder_id=folder_node_id,
                    current_depth=current_depth + 1
                )
            else:
                non_python_type = _determine_non_python_node_type(file_item)
                if non_python_type:
                    _process_non_python_file(
                        ckg=ckg,
                        file_path=file_item,
                        project_root=project_root,
                        parent_folder_id=folder_node_id,
                        current_depth=current_depth + 1,
                        node_type=non_python_type,
                    )
                else:
                    logger.debug(f"Skipping unsupported file: {file_item}")

        for dir_item in dirs:
            _traverse_directory(
                ckg=ckg,
                current_path=dir_item,
                project_root=project_root,
                parent_node_id=folder_node_id,
                current_depth=current_depth + 1,
                root_name=root_name
            )

    except OSError as e:
        logger.error(f"OS error traversing directory {current_path}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error traversing directory {current_path}: {e}", exc_info=True)

def build_ckg_from_path(extracted_code_path: str, root_name: Optional[str] = None) -> CKG:
    """
    Builds the Code Knowledge Graph by traversing the extracted code directory.

    Args:
        extracted_code_path: The absolute path to the root directory
                             containing the extracted Python code.
        root_name: The desired name for the top-level root node (e.g., original zip filename).

    Returns:
        The populated CKG instance.
    """
    logger.info(f"Starting CKG construction from path: {extracted_code_path}")
    ckg = CKG()
    project_root = Path(extracted_code_path).resolve()

    if not project_root.is_dir():
        logger.error(f"Project root path is not a valid directory: {project_root}")
        return ckg

    _traverse_directory(
        ckg=ckg,
        current_path=project_root,
        project_root=project_root,
        parent_node_id=None,
        current_depth=0,
        root_name=root_name
    )

    logger.info(f"Finished initial CKG traversal. Found {len(ckg)} nodes. Max depth: {ckg.max_depth}. Ready for resolution phase.")
    return ckg