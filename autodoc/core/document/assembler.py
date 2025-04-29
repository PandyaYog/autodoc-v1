import logging
from typing import List, Set, Dict
from uuid import UUID
from ..ckg.graph import CKG
from ...models.graph import BaseNode, NodeType
from .formatters import format_node_markdown

logger = logging.getLogger(__name__)

class DocumentAssembler:
    """
    Assembles the final Markdown documentation by traversing the CKG.

    Uses a Depth-First Search (DFS) approach starting from root nodes
    and leverages the formatters to generate Markdown for each node.
    """

    def __init__(self, ckg: CKG):
        """
        Initializes the assembler with the Code Knowledge Graph.

        Args:
            ckg: The populated and summarized CKG instance.
        """
        self.ckg = ckg
        self.markdown_parts: List[str] = []
        self.visited: Set[UUID] = set()

    def _get_and_sort_children(self, node: BaseNode) -> List[UUID]:
        """
        Retrieves and sorts the children of a node for consistent documentation order.

        Sorts Folders first, then Files, then Classes, then Functions, then others,
        alphabetically within each category.
        """
        children: List[BaseNode] = []
        edge_type_to_check = "CONTAINS" 
        if node.node_type == "CLASS":
            edge_type_to_check = "CONTAINS" 

        try:
            children = list(self.ckg.get_successors(node.id, edge_type=edge_type_to_check))
        except KeyError:
            logger.warning(f"Node {node.id} not found while getting successors.")
            return []

        type_order: Dict[NodeType, int] = {
            "FOLDER": 0,
            "FILE": 1,
            "CLASS": 2,
            "FUNCTION": 3, 
            "NON_FUNCTION_NON_CLASS": 4,
        }

        children.sort(key=lambda n: (type_order.get(n.node_type, 99), n.name))

        return [child.id for child in children]


    def _assemble_recursive(self, node_id: UUID, current_heading_level: int):
        """
        Recursive DFS function to assemble Markdown.

        Args:
            node_id: The UUID of the current node to process.
            current_heading_level: The Markdown heading level for this node.
        """
        if node_id in self.visited:
            logger.warning(f"Detected potential cycle or duplicate visit for node {node_id}. Skipping.")
            return

        node = self.ckg.get_node(node_id)
        if not node:
            logger.warning(f"Node with ID {node_id} not found in CKG during assembly. Skipping.")
            return

        logger.debug(f"Assembling node: {node.node_type} '{node.name}' (ID: {node.id}) at level {current_heading_level}")
        self.visited.add(node_id)

        level = min(current_heading_level, 6)
        formatted_markdown = format_node_markdown(node, level)
        self.markdown_parts.append(formatted_markdown)

        if node.node_type in ["FOLDER", "FILE", "CLASS"]:
            children_ids = self._get_and_sort_children(node)
            logger.debug(f"Node {node.id} ('{node.name}') has {len(children_ids)} children to process.")
            for child_id in children_ids:
                self._assemble_recursive(child_id, current_heading_level + 1)


    def assemble(self) -> str:
        """
        Assembles the full Markdown documentation string.

        Returns:
            A single string containing the complete Markdown documentation.
        """
        self.markdown_parts = []
        self.visited = set()
        logger.info("Starting documentation assembly...")

        root_nodes = list(self.ckg.find_nodes(node_type="FOLDER", depth=0))

        if not root_nodes:
            logger.warning("No root nodes (Folder with depth 0) found in CKG. Assembly might be incomplete.")
            if not root_nodes:
                 root_nodes = list(self.ckg.find_nodes(node_type="FILE", depth=0))

        root_nodes.sort(key=lambda n: n.name)

        if not root_nodes:
             logger.error("No root nodes found at all. Cannot assemble document.")
             return "# Documentation Assembly Failed: No Root Nodes Found"

        logger.info(f"Found {len(root_nodes)} root node(s) to start assembly.")

        start_heading_level = 2
        for root_node in root_nodes:
            self._assemble_recursive(root_node.id, start_heading_level)

        logger.info(f"Documentation assembly finished. Assembled {len(self.markdown_parts)} parts.")

        final_markdown = "".join(self.markdown_parts)

        return final_markdown