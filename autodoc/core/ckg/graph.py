import logging
from typing import Optional, List, Dict, Any, Generator, TypeVar, Type, Set
from uuid import UUID
import networkx as nx
from ...models.graph import BaseNode, Edge, EdgeType, NodeType

logger = logging.getLogger(__name__)

TNode = TypeVar('TNode', bound=BaseNode)
class CKG:
    """
    Manages the Code Knowledge Graph (CKG) using networkx.

    Stores nodes (Folders, Files, Code elements) and their relationships (edges).
    Nodes are identified by their UUIDs in the graph.
    Pydantic node models are stored as attributes on the graph nodes
    and also in a separate dictionary for quick lookup.
    """

    def __init__(self):
        """Initializes an empty Code Knowledge Graph."""
        self.graph: nx.DiGraph = nx.DiGraph()
        self._nodes: Dict[UUID, BaseNode] = {}
        self.max_depth: int = 0
        logger.info("Initialized empty Code Knowledge Graph (CKG).")

    def add_node(self, node_data: BaseNode) -> UUID:
        """Adds a node to the CKG."""
        node_id = node_data.id
        if node_id in self._nodes:
            logger.warning(f"Node with ID {node_id} already exists. Overwriting.")
        self._nodes[node_id] = node_data
        self.graph.add_node(node_id, data=node_data)
        self.max_depth = max(self.max_depth, node_data.depth)
        logger.debug(f"Added {node_data.node_type} node: {node_data.name} (ID: {node_id}, Depth: {node_data.depth})")
        return node_id

    def add_edge(self, source_id: UUID, target_id: UUID, type: EdgeType, label: Optional[str] = None):
        """Adds a directed edge between two nodes in the CKG."""
        if source_id not in self._nodes:
            raise KeyError(f"Source node with ID {source_id} not found in CKG.")
        if target_id not in self._nodes:
            raise KeyError(f"Target node with ID {target_id} not found in CKG.")

        self.graph.add_edge(source_id, target_id, type=type, label=label)

        edge_model = Edge(source_id=source_id, target_id=target_id, type=type, label=label)
        source_node_data = self._nodes[source_id]
        source_node_data.edges.append(edge_model)

        logger.debug(f"Added edge: {source_id} --[{type}]--> {target_id} (Label: {label})")

    def get_node(self, node_id: UUID) -> Optional[BaseNode]:
        """Retrieves a node's Pydantic data model by its ID."""
        return self._nodes.get(node_id)

    def get_node_nx_data(self, node_id: UUID) -> Optional[Dict[str, Any]]:
        """Retrieves the raw attribute dictionary of a node from the networkx graph."""
        if node_id in self.graph:
            return self.graph.nodes[node_id]
        return None

    def get_all_nodes(self) -> List[BaseNode]:
        """Returns a list of all Pydantic node models in the graph."""
        return list(self._nodes.values())

    def find_nodes(
        self,
        node_type: Optional[NodeType] = None,
        depth: Optional[int] = None,
        **attributes: Any
    ) -> Generator[BaseNode, None, None]:
        """
        Finds nodes matching specified criteria by iterating through stored models.
        This can be less efficient for large graphs if used frequently for indexed lookups.
        """
        for node in self._nodes.values():
            match = True
            if node_type is not None and node.node_type != node_type:
                match = False
                continue
            if depth is not None and node.depth != depth:
                match = False
                continue
            for key, value in attributes.items():
                node_value = getattr(node, key, None)
                if node_value != value:
                    match = False
                    break
            if match:
                yield node

    def get_children_by_parent(self, parent_id: UUID) -> Generator[BaseNode, None, None]:
        """
        Efficiently retrieves direct structural children of a parent node.

        Uses the 'IS_PART_OF' edges pointing from child to parent.
        """
        if parent_id not in self.graph:
            logger.warning(f"Parent node {parent_id} not found in graph for get_children_by_parent.")
            return

        processed_children: Set[UUID] = set()
        for child_id, _, edge_data in self.graph.in_edges(parent_id, data=True):
            if edge_data.get('type') == "IS_PART_OF":
                if child_id not in processed_children:
                    child_node = self.get_node(child_id)
                    if child_node:
                        yield child_node
                        processed_children.add(child_id)
                    else:
                        logger.error(f"Edge IS_PART_OF exists from non-existent node {child_id} to parent {parent_id}")

    def get_successors(self, node_id: UUID, edge_type: Optional[EdgeType] = None) -> Generator[BaseNode, None, None]:
        """Yields successor nodes (nodes pointed to by outgoing edges) of a given node."""
        if node_id not in self.graph:
            return
        for _, target_id, edge_data in self.graph.out_edges(node_id, data=True):
            if edge_type is None or edge_data.get('type') == edge_type:
                target_node = self.get_node(target_id)
                if target_node:
                    yield target_node

    def get_predecessors(self, node_id: UUID, edge_type: Optional[EdgeType] = None) -> Generator[BaseNode, None, None]:
        """Yields predecessor nodes (nodes pointing to the given node) of a given node."""
        if node_id not in self.graph:
            return
        for source_id, _, edge_data in self.graph.in_edges(node_id, data=True):
            if edge_type is None or edge_data.get('type') == edge_type:
                source_node = self.get_node(source_id)
                if source_node:
                    yield source_node

    def get_out_edges(self, node_id: UUID, edge_type: Optional[EdgeType] = None) -> Generator[Edge, None, None]:
        """Yields outgoing Edge models from a given node."""
        node = self.get_node(node_id)
        if node:
            for edge in node.edges:
                if edge_type is None or edge.type == edge_type:
                    yield edge

    def get_in_edges(self, node_id: UUID, edge_type: Optional[EdgeType] = None) -> Generator[Edge, None, None]:
        """Yields incoming Edge models pointing to a given node."""
        if node_id not in self.graph:
            return
        for source_id, target_id, edge_data in self.graph.in_edges(node_id, data=True):
            if target_id == node_id and (edge_type is None or edge_data.get('type') == edge_type):
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=edge_data.get('type'),
                    label=edge_data.get('label')
                )

    def __len__(self) -> int:
        """Returns the number of nodes in the graph."""
        return len(self._nodes)

    def __contains__(self, node_id: UUID) -> bool:
        """Checks if a node ID exists in the graph."""
        return node_id in self._nodes