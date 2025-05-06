import logging
from typing import List, Set, Dict
from uuid import UUID
from ..ckg.graph import CKG
from ...models.graph import BaseNode, NodeType
from .formatters import format_node_markdown
from ...models.graph import (
    BaseNode, FolderNode, FileNode, ClassNode, FunctionNode,
    ImportBlockNode, NonFunctionNonClassNode, NodeType
)

logger = logging.getLogger(__name__)

class DocumentAssembler:
    """
    Assembles the final Markdown documentation by traversing the CKG.

    Uses DFS for folders and iterative line-based processing for files
    to ensure documentation follows source code order within files.
    """

    def __init__(self, ckg: CKG):
        """
        Initializes the assembler with the Code Knowledge Graph.
        """
        self.ckg = ckg
        self.markdown_parts: List[str] = []
        self.visited_folders: Set[UUID] = set()

    def _get_folder_children_sorted(self, node: FolderNode) -> List[UUID]:
        """
        Retrieves and sorts the children (Files/Folders) of a FolderNode.
        Sorts Folders first, then Files, alphabetically within each category.
        """
        children: List[BaseNode] = []
        try:
            children = list(self.ckg.get_successors(node.id, edge_type="CONTAINS"))
        except KeyError:
            logger.warning(f"Node {node.id} not found while getting successors.")
            return []

        children = [c for c in children if c.node_type in ["FOLDER", "FILE"]]
        type_order: Dict[NodeType, int] = {"FOLDER": 0, "FILE": 1}
        children.sort(key=lambda n: (type_order.get(n.node_type, 99), n.name))
        return [child.id for child in children]

    def _get_file_children_sorted_by_line(self, node: FileNode) -> List[BaseNode]:
        """
        Retrieves and sorts the direct code children of a FileNode by start line.
        Includes ImportBlock, Class, Function (top-level), NonFunctionNonClass.
        """
        children: List[BaseNode] = []
        try:
            children = list(self.ckg.find_nodes(belongs_to=node.id))
        except Exception as e:
            logger.error(f"Error finding children for FileNode {node.id} ('{node.name}'): {e}", exc_info=True)
            return []

        relevant_children = []
        for child in children:
            if child.node_type in ["IMPORT_BLOCK", "CLASS", "FUNCTION", "NON_FUNCTION_NON_CLASS"]:
                if hasattr(child, 'start_line') and child.start_line is not None:
                    relevant_children.append(child)
                else:
                    logger.warning(f"Node {child.id} ('{child.name}') of type {child.node_type} belonging to file {node.name} is missing start_line. Skipping in line sort.")

        relevant_children.sort(key=lambda n: n.start_line)
        return relevant_children

    def _get_class_methods_sorted_by_line(self, node: ClassNode) -> List[FunctionNode]:
        """Retrieves and sorts methods of a ClassNode by start line."""
        methods: List[FunctionNode] = []
        try:
            potential_methods = list(self.ckg.find_nodes(node_type="FUNCTION", belongs_to=node.id))
            for method in potential_methods:
                if isinstance(method, FunctionNode) and method.is_method and method.start_line is not None:
                    methods.append(method)
        except Exception as e:
            logger.error(f"Error finding methods for ClassNode {node.id} ('{node.name}'): {e}", exc_info=True)
            return []

        methods.sort(key=lambda n: n.start_line)
        return methods

    def _assemble_recursive(self, node_id: UUID, current_heading_level: int):
        """
        Recursive/Iterative function to assemble Markdown. Handles folders via
        recursion and files via iterative line-based processing.
        """
        node = self.ckg.get_node(node_id)
        if not node:
            logger.warning(f"Node with ID {node_id} not found in CKG during assembly. Skipping.")
            return

        level = min(current_heading_level, 6)

        if isinstance(node, FolderNode):
            if node_id in self.visited_folders:
                logger.warning(f"Detected potential cycle or duplicate visit for folder {node_id}. Skipping.")
                return
            self.visited_folders.add(node_id)

            logger.debug(f"Assembling FOLDER: {node.name} (ID: {node.id}) at level {level}")
            formatted_markdown = format_node_markdown(node, level)
            self.markdown_parts.append(formatted_markdown)

            children_ids = self._get_folder_children_sorted(node)
            for child_id in children_ids:
                self._assemble_recursive(child_id, current_heading_level + 1)

        elif isinstance(node, FileNode):
            logger.debug(f"Assembling FILE: {node.name} (ID: {node.id}) at level {level}")
            formatted_markdown = format_node_markdown(node, level)
            self.markdown_parts.append(formatted_markdown)

            file_children = self._get_file_children_sorted_by_line(node)
            processed_method_ids: Set[UUID] = set()

            for child_node in file_children:
                child_level = current_heading_level + 1

                if isinstance(child_node, ClassNode):
                    logger.debug(f"  Processing CLASS child: {child_node.name}")
                    class_markdown = format_node_markdown(child_node, child_level)
                    self.markdown_parts.append(class_markdown)

                    methods = self._get_class_methods_sorted_by_line(child_node)
                    logger.debug(f"    Found {len(methods)} methods for class {child_node.name}")
                    for method_node in methods:
                        if method_node.id not in processed_method_ids:
                            logger.debug(f"    Processing METHOD child: {method_node.name}")
                            method_markdown = format_node_markdown(method_node, child_level + 1)
                            self.markdown_parts.append(method_markdown)
                            processed_method_ids.add(method_node.id)
                        else:
                            logger.warning(f"Method {method_node.id} ('{method_node.name}') seems to be processed already?")

                elif isinstance(child_node, FunctionNode):
                    if child_node.id not in processed_method_ids:
                        logger.debug(f"  Processing FUNCTION child: {child_node.name}")
                        func_markdown = format_node_markdown(child_node, child_level)
                        self.markdown_parts.append(func_markdown)

                elif isinstance(child_node, (ImportBlockNode, NonFunctionNonClassNode)):
                    logger.debug(f"  Processing {child_node.node_type} child: {child_node.name}")
                    block_markdown = format_node_markdown(child_node, child_level)
                    self.markdown_parts.append(block_markdown)

        else:
            logger.warning(f"Unexpected node type encountered at top level of assembly: {node.node_type} ('{node.name}'). Formatting individually.")
            formatted_markdown = format_node_markdown(node, level)
            self.markdown_parts.append(formatted_markdown)

    def assemble(self) -> str:
        """
        Assembles the full Markdown documentation string.
        """
        self.markdown_parts = []
        self.visited_folders = set()
        logger.info("Starting documentation assembly...")

        root_nodes: List[BaseNode] = []
        root_nodes.extend(list(self.ckg.find_nodes(node_type="FOLDER", depth=0)))
        if not root_nodes:
            root_nodes.extend(list(self.ckg.find_nodes(node_type="FILE", depth=0)))

        root_nodes.sort(key=lambda n: n.name)

        if not root_nodes:
            logger.error("No root nodes (depth 0) found. Cannot assemble document.")
            return "# Documentation Assembly Failed: No Root Nodes Found"

        logger.info(f"Found {len(root_nodes)} root node(s) to start assembly.")

        start_heading_level = 2
        for root_node in root_nodes:
            self._assemble_recursive(root_node.id, start_heading_level)

        logger.info(f"Documentation assembly finished. Assembled {len(self.markdown_parts)} parts.")
        final_markdown = "".join(self.markdown_parts)
        return final_markdown