from typing import Dict, Any, Union, List, Optional
from pydantic import TypeAdapter
from ..models.graph import (
    Edge,
    BaseNode,
    FolderNode,
    FileNode,
    ClassNode,
    FunctionNode,
    NonFunctionNonClassNode,
    NodeType,
    EdgeType,
)

edge_schema: Dict[str, Any] = Edge.model_json_schema()
base_node_schema: Dict[str, Any] = BaseNode.model_json_schema()
folder_node_schema: Dict[str, Any] = FolderNode.model_json_schema()
file_node_schema: Dict[str, Any] = FileNode.model_json_schema()
class_node_schema: Dict[str, Any] = ClassNode.model_json_schema()
function_node_schema: Dict[str, Any] = FunctionNode.model_json_schema()
non_function_non_class_node_schema: Dict[str, Any] = NonFunctionNonClassNode.model_json_schema()

AnyNode = Union[FolderNode, FileNode, ClassNode, FunctionNode, NonFunctionNonClassNode]

any_node_adapter = TypeAdapter(AnyNode)
any_node_schema: Dict[str, Any] = any_node_adapter.json_schema()

list_of_nodes_adapter = TypeAdapter(List[AnyNode])
list_of_nodes_schema: Dict[str, Any] = list_of_nodes_adapter.json_schema()

_schemas_by_type = {
    "FOLDER": folder_node_schema,
    "FILE": file_node_schema,
    "CLASS": class_node_schema,
    "FUNCTION": function_node_schema,
    "NON_FUNCTION_NON_CLASS": non_function_non_class_node_schema,
    "EDGE": edge_schema,
    "ANY_NODE": any_node_schema,
    "NODE_LIST": list_of_nodes_schema,
}

def get_ckg_schema(schema_type: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a specific pre-generated JSON schema.

    Args:
        schema_type: The type of schema to retrieve (e.g., "FOLDER", "FILE", "EDGE", "ANY_NODE").

    Returns:
        The JSON schema as a dictionary, or None if the type is invalid.
    """
    return _schemas_by_type.get(schema_type.upper())
