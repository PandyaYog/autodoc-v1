import ast
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
    NodeType
)

logger = logging.getLogger(__name__)

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


def _process_file(
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

    logger.debug(f"Finished processing file: {file_path}")

def _traverse_directory(
    ckg: CKG,
    current_path: Path,
    project_root: Path,
    parent_node_id: Optional[UUID],
    current_depth: int
):
    """
    Recursively traverses directories using DFS, processing files and subdirectories.
    """
    if not current_path.is_dir():
        logger.warning(f"Traversal path is not a directory: {current_path}. Skipping.")
        return

    logger.debug(f"Traversing directory: {current_path} at depth {current_depth}")
    relative_path = current_path.relative_to(project_root)

    folder_node = FolderNode(
        name=current_path.name,
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
                _process_file(
                    ckg=ckg,
                    file_path=file_item,
                    project_root=project_root,
                    parent_folder_id=folder_node_id,
                    current_depth=current_depth + 1
                )
            else:
                logger.debug(f"Skipping non-Python file: {file_item}")

        for dir_item in dirs:
            _traverse_directory(
                ckg=ckg,
                current_path=dir_item,
                project_root=project_root,
                parent_node_id=folder_node_id,
                current_depth=current_depth + 1
            )

    except OSError as e:
        logger.error(f"OS error traversing directory {current_path}: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error traversing directory {current_path}: {e}", exc_info=True)


def build_ckg_from_path(extracted_code_path: str) -> CKG:
    """
    Builds the Code Knowledge Graph by traversing the extracted code directory.

    Args:
        extracted_code_path: The absolute path to the root directory
                             containing the extracted Python code.

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
        current_depth=0
    )

    logger.info(f"Finished initial CKG traversal. Found {len(ckg)} nodes. Max depth: {ckg.max_depth}. Ready for resolution phase.")
    return ckg