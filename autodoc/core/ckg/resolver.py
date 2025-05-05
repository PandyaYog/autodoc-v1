import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Set, Any
from uuid import UUID
from .graph import CKG
from ...models.graph import NodeType, EdgeType, FileNode, ImportBlockNode, ClassNode, FunctionNode, BaseNode, NonFunctionNonClassNode

logger = logging.getLogger(__name__)


def _find_node_by_module_path(ckg: CKG, module_path: str) -> Optional[UUID]:
    """Finds the UUID of a FileNode matching a given module path."""
    for node in ckg.find_nodes(node_type="FILE", module_path=module_path):
        return node.id
    return None

def _find_class_node_by_name(ckg: CKG, class_name: str) -> List[UUID]:
    """Finds UUIDs of ClassNodes matching a given name (can be multiple)."""
    matching_ids = []
    for node in ckg.find_nodes(node_type="CLASS", name=class_name):
        matching_ids.append(node.id)
    return matching_ids

def _find_function_node_by_name(ckg: CKG, function_name: str) -> List[UUID]:
    """Finds UUIDs of FunctionNodes matching a given name (can be multiple)."""
    matching_ids = []
    for node in ckg.find_nodes(node_type="FUNCTION", name=function_name):
         matching_ids.append(node.id)
    return matching_ids

def _resolve_relative_import(
    current_module_path: Optional[str],
    level: int,
    imported_module_name: Optional[str]
) -> Optional[str]:
    """Resolves a relative import path to an absolute module path."""
    if level == 0: 
        return imported_module_name

    if current_module_path is None:
        logger.warning(f"Cannot resolve relative import with level {level} from unknown module path.")
        return None

    current_parts = current_module_path.split('.')

    if level > len(current_parts):
        logger.warning(f"Relative import level {level} goes beyond top-level package from '{current_module_path}'.")
        return None 

    base_parts = current_parts[:len(current_parts) - (level -1)] 

    if imported_module_name:
        target_parts = base_parts + [imported_module_name]
    else: 
         target_parts = base_parts

    return ".".join(target_parts)


def _resolve_imports(ckg: CKG):
    """Resolves IMPORTS edges between FileNodes based on ImportBlockNodes."""
    logger.info("Starting import resolution...")
    resolved_count = 0
    for file_node in list(ckg.find_nodes(node_type="FILE")):
        current_module_path = file_node.module_path
        import_block_node: Optional[ImportBlockNode] = None
        imports_data: List[Dict[str, Any]] = []

        for child_node in ckg.get_successors(file_node.id, edge_type="CONTAINS"):
            if isinstance(child_node, ImportBlockNode):
                import_block_node = child_node
                imports_data = import_block_node.imports 
                break

        if not imports_data:
            logger.debug(f"No imports found for file: {file_node.file_path}")
            continue 

        import_aliases: Dict[str, str] = {} 
        file_node_nx = ckg.get_node_nx_data(file_node.id) 

        for imp in imports_data:
            target_module_str: Optional[str] = None
            imported_item_name: Optional[str] = imp.get("name")
            alias: Optional[str] = imp.get("alias")

            if imp["type"] == "import":
                target_module_str = imported_item_name
                if alias:
                    import_aliases[alias] = target_module_str
                else:
                    import_aliases[imported_item_name] = target_module_str
            elif imp["type"] == "from":
                level = imp.get("level", 0)
                module_name = imp.get("module")
                base_module_path = _resolve_relative_import(current_module_path, level, module_name)

                if base_module_path is None: continue

                if imported_item_name == "*":
                    target_module_str = base_module_path 
                    logger.debug(f"Wildcard import detected from '{target_module_str}' in {file_node.file_path}.")
                else:
                    target_item_path = f"{base_module_path}.{imported_item_name}"
                    target_file_module_str = base_module_path 
                    effective_name = alias if alias else imported_item_name
                    if effective_name:
                         import_aliases[effective_name] = target_item_path
                         import_aliases[f"{effective_name}__base_module"] = target_file_module_str

                    target_file_id = _find_node_by_module_path(ckg, target_file_module_str)
                    if target_file_id:
                        ckg.add_edge(file_node.id, target_file_id, type="IMPORTS", label=f"from {target_file_module_str} import {imported_item_name}")
                        resolved_count += 1
                    else:
                        logger.debug(f"Could not resolve imported module file: '{target_file_module_str}' for 'from' import in {file_node.file_path}")
                    continue 
                
            if target_module_str:
                target_file_id = _find_node_by_module_path(ckg, target_module_str)
                if target_file_id:
                    ckg.add_edge(file_node.id, target_file_id, type="IMPORTS", label=alias)
                    resolved_count += 1
                else:
                    logger.debug(f"Could not resolve imported module file: '{target_module_str}' in {file_node.file_path}")

        if file_node_nx:
            file_node_nx['import_aliases'] = import_aliases
        else:
             logger.warning(f"Could not retrieve networkx data for FileNode {file_node.id} to store import aliases.")

    logger.info(f"Import resolution finished. Added {resolved_count} IMPORTS edges.")

def _resolve_inheritance(ckg: CKG):
    """Resolves INHERITS_FROM edges between ClassNodes."""
    logger.info("Starting inheritance resolution...")
    resolved_count = 0
    for class_node in list(ckg.find_nodes(node_type="CLASS")):
        containing_file_id = class_node.belongs_to
        file_node_nx = ckg.get_node_nx_data(containing_file_id)

        if not file_node_nx or 'ast_classes' not in file_node_nx:
            logger.warning(f"AST class details not found for file {containing_file_id} containing class {class_node.name}. Skipping inheritance resolution.")
            continue

        ast_classes = file_node_nx['ast_classes']
        base_names: List[str] = []
        for cls_data in ast_classes:
            if cls_data["name"] == class_node.name and cls_data["start_line"] == class_node.start_line:
                base_names = cls_data.get("bases", [])
                break

        if not base_names:
            continue

        for base_name in base_names:
            matching_parent_ids = _find_class_node_by_name(ckg, base_name)
            if not matching_parent_ids:
                logger.debug(f"Could not resolve base class '{base_name}' for class '{class_node.name}' in {class_node.file_path}.")
            else:
                for parent_id in matching_parent_ids:
                    if parent_id == class_node.id:
                        continue
                    try:
                        ckg.add_edge(class_node.id, parent_id, type="INHERITS_FROM")
                        resolved_count += 1
                        logger.debug(f"Resolved inheritance: {class_node.name} --[INHERITS_FROM]--> {base_name} ({parent_id})")
                    except KeyError as e:
                        logger.error(f"Error adding INHERITS_FROM edge from {class_node.id} to {parent_id}: {e}")
                if len(matching_parent_ids) > 1:
                    logger.warning(f"Class '{class_node.name}' inherits from '{base_name}', which resolved to multiple nodes: {matching_parent_ids}. Added edges to all.")

    logger.info(f"Inheritance resolution finished. Added {resolved_count} INHERITS_FROM edges.")

def _resolve_calls(ckg: CKG):
    """Resolves CALLS edges between Function/Method nodes."""
    logger.info("Starting call resolution...")
    resolved_count = 0
    unresolved_count = 0

    for file_node in list(ckg.find_nodes(node_type="FILE")):
        file_node_nx = ckg.get_node_nx_data(file_node.id)
        if not file_node_nx or 'ast_calls' not in file_node_nx or 'node_map' not in file_node_nx:
            continue

        calls_data = file_node_nx['ast_calls']
        node_map = file_node_nx['node_map']
        import_aliases = file_node_nx.get('import_aliases', {})

        for call in calls_data:
            caller_type = call["caller_type"]
            caller_name = call["caller_name"]
            caller_lines = tuple(call["caller_lines"])
            call_name_str = call["call_name"]
            call_line = call["line"]

            caller_node_id: Optional[UUID] = None
            if caller_type == "FILE":
                caller_node_id = file_node.id
            elif caller_type in ["FUNCTION", "CLASS", "TOP_LEVEL"]:
                map_key: Optional[Tuple] = None
                if caller_type == "FUNCTION":
                    map_key = ("FUNCTION", caller_name, caller_lines[0])
                elif caller_type == "CLASS":
                    map_key = ("CLASS", caller_name, caller_lines[0])
                elif caller_type == "TOP_LEVEL":
                    for node in ckg.find_nodes(node_type="NON_FUNCTION_NON_CLASS", name=caller_name, start_line=caller_lines[0]):
                        if node.belongs_to == file_node.id:
                            caller_node_id = node.id
                            break
                if map_key and map_key in node_map:
                    caller_node_id = node_map[map_key]

            if not caller_node_id:
                logger.warning(f"Could not find caller node for call '{call_name_str}' at {file_node.file_path}:{call_line} (Caller context: {caller_type} '{caller_name}' L{caller_lines[0]})")
                continue

            target_node_ids: List[UUID] = []
            potential_key_prefix = ("FUNCTION", call_name_str)
            for (ntype, nname, nline), nid in node_map.items():
                if ntype == "FUNCTION" and nname == call_name_str:
                    target_node_ids.append(nid)
                    logger.debug(f"Call resolution: Found '{call_name_str}' in same file ({nid})")
                    break

            if not target_node_ids:
                parts = call_name_str.split('.', 1)
                first_part = parts[0]
                rest_part = parts[1] if len(parts) > 1 else None
                if first_part in import_aliases:
                    resolved_import_target = import_aliases[first_part]
                    base_module_path = import_aliases.get(f"{first_part}__base_module", resolved_import_target)
                    target_file_id = _find_node_by_module_path(ckg, base_module_path)
                    if target_file_id:
                        target_file_node = ckg.get_node(target_file_id)
                        target_file_nx = ckg.get_node_nx_data(target_file_id)
                        if target_file_nx and 'node_map' in target_file_nx:
                            target_node_map = target_file_nx['node_map']
                            func_name_to_find = rest_part if rest_part else first_part
                            if func_name_to_find:
                                for (ntype, nname, nline), nid in target_node_map.items():
                                    if ntype == "FUNCTION" and nname == func_name_to_find:
                                        target_node_ids.append(nid)
                                        logger.debug(f"Call resolution: Found imported '{call_name_str}' in {target_file_node.name} ({nid})")
                                        break

            if target_node_ids:
                for target_id in target_node_ids:
                    if caller_node_id == target_id:
                        continue
                    try:
                        ckg.add_edge(caller_node_id, target_id, type="CALLS")
                        resolved_count += 1
                    except KeyError as e:
                        logger.error(f"Error adding CALLS edge from {caller_node_id} to {target_id}: {e}")
            else:
                logger.debug(f"Could not resolve call target '{call_name_str}' from {caller_type} '{caller_name}' in {file_node.file_path}:{call_line}")
                unresolved_count += 1

    logger.info(f"Call resolution finished. Added {resolved_count} CALLS edges. {unresolved_count} calls unresolved.")


def _resolve_used_imports(ckg: CKG):
    """Resolves USES_IMPORT edges from CodeNodes to imported FileNodes."""
    logger.info("Starting used import resolution...")
    resolved_count = 0
    processed_nodes: Set[UUID] = set()

    code_node_types: List[NodeType] = ["FUNCTION", "CLASS", "NON_FUNCTION_NON_CLASS"]
    for node_type in code_node_types:
        for code_node in list(ckg.find_nodes(node_type=node_type)):
            if code_node.id in processed_nodes:
                continue

            containing_file_id: Optional[UUID] = None
            if isinstance(code_node, (FunctionNode, NonFunctionNonClassNode, ClassNode)):
                parent_id = code_node.belongs_to
                parent_node = ckg.get_node(parent_id)
                if parent_node:
                    if parent_node.node_type == "FILE":
                        containing_file_id = parent_id
                    elif parent_node.node_type == "CLASS":
                        containing_file_id = parent_node.belongs_to

            if not containing_file_id:
                logger.warning(f"Could not find containing file for CodeNode {code_node.name} ({code_node.id}). Skipping used import resolution.")
                processed_nodes.add(code_node.id)
                continue

            file_node_nx = ckg.get_node_nx_data(containing_file_id)
            if not file_node_nx or 'import_aliases' not in file_node_nx:
                logger.warning(f"Import aliases not found for file {containing_file_id} containing node {code_node.name}. Skipping used import resolution.")
                processed_nodes.add(code_node.id)
                continue
            import_aliases = file_node_nx['import_aliases']

            used_names_in_code: List[str] = getattr(code_node, 'imports_used', [])
            if not hasattr(code_node, 'imports_used'):
                logger.warning(f"'imports_used' attribute not found on {node_type} node {code_node.name}. Requires update in traversal.py")
                processed_nodes.add(code_node.id)
                continue

            if not used_names_in_code:
                processed_nodes.add(code_node.id)
                continue

            imported_file_ids: Set[UUID] = {
                target_node.id for target_node in ckg.get_successors(containing_file_id, edge_type="IMPORTS")
                if target_node.node_type == "FILE"
            }

            for name in used_names_in_code:
                target_path = import_aliases.get(name)
                base_module_path = import_aliases.get(f"{name}__base_module", target_path)
                parts = name.split('.', 1)
                if not target_path and parts[0] in import_aliases:
                    target_path = import_aliases[parts[0]]
                    base_module_path = import_aliases.get(f"{parts[0]}__base_module", target_path)

                if base_module_path:
                    target_file_id = _find_node_by_module_path(ckg, base_module_path)
                    if target_file_id and target_file_id in imported_file_ids:
                        edge_exists = any(edge.target_id == target_file_id for edge in ckg.get_out_edges(code_node.id, edge_type="USES_IMPORT"))
                        if not edge_exists:
                            try:
                                ckg.add_edge(code_node.id, target_file_id, type="USES_IMPORT")
                                resolved_count += 1
                            except KeyError as e:
                                logger.error(f"Error adding USES_IMPORT edge from {code_node.id} to {target_file_id}: {e}")

            processed_nodes.add(code_node.id)

    logger.info(f"Used import resolution finished. Added {resolved_count} USES_IMPORT edges.")

def _cleanup_temporary_data(ckg: CKG):
    """Removes temporary data attached to nodes after resolution."""
    logger.info("Cleaning up temporary AST/resolver data from CKG nodes...")
    count = 0
    for node in list(ckg.find_nodes(node_type="FILE")):
        node_attrs = ckg.get_node_nx_data(node.id)
        if node_attrs:
            keys_to_remove = ['ast_calls', 'node_map', 'import_aliases', 'ast_classes']
            removed_key = False
            for key in keys_to_remove:
                if key in node_attrs:
                    del node_attrs[key]
                    removed_key = True
            if removed_key:
                count += 1

    logger.info(f"Removed temporary data from {count} FileNodes.")

def resolve_ckg_edges(ckg: CKG):
    """
    Resolves non-structural edges (IMPORTS, INHERITS_FROM, CALLS, USES_IMPORT)
    in the CKG after initial traversal.

    Modifies the CKG instance in place.

    Args:
        ckg: The CKG instance populated by the traversal phase.
    """
    if not ckg or len(ckg) == 0:
        logger.warning("CKG is empty. Skipping resolution phase.")
        return

    logger.info("Starting CKG resolution phase...")

    _resolve_imports(ckg)
    _resolve_inheritance(ckg)
    _resolve_calls(ckg)
    _resolve_used_imports(ckg)
    _cleanup_temporary_data(ckg)

    logger.info("CKG resolution phase completed.")