# scripts/visualize_ckg.py
# NOTE: This script assumes the 'autodoc' package has been installed
# in the current Python environment (e.g., using 'pip install .' or 'pip install -e .')

import networkx as nx
import matplotlib.pyplot as plt
import sys
import os
import json
import zipfile
import tempfile
import asyncio
from uuid import UUID
from pathlib import Path

try:
    from autodoc.core.extraction.extractor import extract_code
    from autodoc.core.extraction.exceptions import ExtractionException
    from autodoc.core.ckg.traversal import build_ckg_from_path
    from autodoc.core.ckg.resolver import resolve_ckg_edges
    from autodoc.models.graph import BaseNode
    from autodoc.config import settings 
except ImportError as e:
    print(f"Import Error: {e}")
    print("Please ensure the 'autodoc' package is installed in your environment.")
    print("You can typically install it by running 'pip install .' or 'pip install -e .' from the project root directory.")
    sys.exit(1)

def visualize_matplotlib(ckg_graph: nx.DiGraph, output_file="ckg_matplotlib.png"):
    """Visualizes the CKG using Matplotlib, including distinct edges."""
    if not ckg_graph or ckg_graph.number_of_nodes() == 0:
        print("Graph is empty or has no nodes, cannot visualize.")
        return

    plt.figure(figsize=(30, 30)) 

    try:
        pos = nx.kamada_kawai_layout(ckg_graph)
    except Exception as e:
        print(f"Layout failed ({e}), falling back to random layout.")
        pos = nx.random_layout(ckg_graph, seed=42) 

    labels = {}
    colors = []
    node_sizes = []
    color_map = {
        "FOLDER": "skyblue",
        "FILE": "lightgreen",
        "IMPORT_BLOCK": "palegreen",
        "CLASS": "lightcoral",
        "FUNCTION": "orange",
        "NON_FUNCTION_NON_CLASS": "mediumpurple",
    }
    node_id_map = {node_id: node_id for node_id in ckg_graph.nodes()}

    for node_id, data in ckg_graph.nodes(data=True):
        node_data: BaseNode = data.get('data')
        dict_key = node_id_map[node_id] 

        if node_data:
            label_name = node_data.name[:20] + '...' if len(node_data.name) > 20 else node_data.name
            labels[dict_key] = f"{node_data.node_type[0]}:{label_name}"
            colors.append(color_map.get(node_data.node_type, "grey"))
            node_sizes.append(300 + node_data.depth * 50)
        else:
            label_text = str(node_id)
            labels[dict_key] = label_text[:8] if isinstance(node_id, UUID) else label_text
            colors.append("grey")
            node_sizes.append(300)

    nx.draw_networkx_nodes(ckg_graph, pos,
                           node_color=colors,
                           node_size=node_sizes,
                           alpha=0.9)

    edge_colors = []
    edge_styles = []
    edge_widths = []
    edge_color_map = {
        "CONTAINS": "black",
        "IS_PART_OF": "lightgrey",
        "DEFINED_IN": "darkgrey",
        "METHOD_OF": "darkgrey",
        "CALLS": "red",
        "IMPORTS": "blue",
        "INHERITS_FROM": "green",
        "USES_IMPORT": "cyan",
    }
    edge_style_map = {
        "CONTAINS": "solid",
        "IS_PART_OF": "dashed",
        "DEFINED_IN": "solid",
        "METHOD_OF": "solid",
        "CALLS": "solid",
        "IMPORTS": "dotted",
        "INHERITS_FROM": "solid",
        "USES_IMPORT": "dotted",
    }
    edge_width_map = {
        "CONTAINS": 1.0,
        "IS_PART_OF": 0.5,
        "DEFINED_IN": 0.8,
        "METHOD_OF": 0.8,
        "CALLS": 1.2,
        "IMPORTS": 0.8,
        "INHERITS_FROM": 1.5,
        "USES_IMPORT": 0.7,
    }

    for u, v, data in ckg_graph.edges(data=True):
        edge_type = data.get('type', '')
        edge_colors.append(edge_color_map.get(edge_type, 'grey'))
        edge_styles.append(edge_style_map.get(edge_type, 'dashed'))
        edge_widths.append(edge_width_map.get(edge_type, 0.5))

    nx.draw_networkx_edges(ckg_graph, pos,
                           edge_color=edge_colors,
                           style=edge_styles,
                           width=edge_widths,
                           alpha=0.6,
                           arrows=True,
                           arrowstyle='-|>', 
                           arrowsize=10,
                           connectionstyle='arc3,rad=0.1')

    nx.draw_networkx_labels(ckg_graph, pos, labels=labels, font_size=7, font_weight='bold')

    edge_labels = {}
    for u, v, data in ckg_graph.edges(data=True):
        edge_type = data.get('type')
        if edge_type in ["CALLS", "IMPORTS", "INHERITS_FROM"]:
             edge_labels[(node_id_map[u], node_id_map[v])] = edge_type[0] 

    nx.draw_networkx_edge_labels(
        ckg_graph, pos,
        edge_labels=edge_labels,
        font_size=5,
        font_color='purple',
        label_pos=0.3 
    )

    plt.title("Code Knowledge Graph Visualization (Matplotlib)", size=16)
    plt.axis('off') 
    try:
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Graph saved to {output_file}")
    except Exception as e:
        print(f"Error saving graph image: {e}")

def export_ckg_to_json(ckg_graph: nx.DiGraph, output_file="ckg_data.json"):
    """Exports the CKG data (including node metadata) to a JSON file."""
    if not ckg_graph:
        print("Graph is empty, cannot export.")
        return

    try:
        graph_data = nx.node_link_data(ckg_graph)

        for node_dict in graph_data.get('nodes', []):
            node_id_from_dict = node_dict.get('id')
            nx_node_data_dict = ckg_graph.nodes.get(node_id_from_dict)

            if nx_node_data_dict and 'data' in nx_node_data_dict and isinstance(nx_node_data_dict['data'], BaseNode):
                node_dict['data'] = nx_node_data_dict['data'].model_dump(mode='json', exclude_none=True)
            elif 'data' in node_dict:
                 del node_dict['data']

            if 'id' in node_dict:
                 node_dict['id'] = str(node_dict['id'])

        for link_dict in graph_data.get('links', []):
             if 'source' in link_dict: link_dict['source'] = str(link_dict['source'])
             if 'target' in link_dict: link_dict['target'] = str(link_dict['target'])

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(graph_data, f, indent=2, ensure_ascii=False)

        print(f"Graph data exported to {output_file}")

    except Exception as e:
        print(f"Error exporting graph to JSON: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/visualize_ckg.py <path_to_code_directory_or_zip>")
        sys.exit(1)

    input_path = sys.argv[1]
    is_zip = zipfile.is_zipfile(input_path) if os.path.exists(input_path) else False
    extracted_path_to_use = None
    temp_dir_context_manager = None

    class MockUploadFile:
        def __init__(self, filepath):
            self.filename = os.path.basename(filepath)
            self._file = open(filepath, 'rb')
        async def read(self): return self._file.read()
        async def seek(self, offset, whence=0): return self._file.seek(offset, whence)
        def tell(self): return self._file.tell()
        def close(self): self._file.close()
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): self.close()

    try:
        if is_zip:
            print(f"Input is a ZIP file: {input_path}")
            temp_dir_context_manager = tempfile.TemporaryDirectory(
                prefix="autodoc_viz_",
                dir=getattr(settings, 'temp_dir_base', None) 
            )
            extraction_path = temp_dir_context_manager.name
            print(f"Extracting to temporary directory: {extraction_path}")

            async def extract_zip():
                 async with MockUploadFile(input_path) as mock_upload_file:
                    await extract_code(mock_upload_file, extraction_path, settings)

            asyncio.run(extract_zip())
            extracted_path_to_use = extraction_path
            print("Extraction complete.")

        elif os.path.isdir(input_path):
            print(f"Input is a directory: {input_path}")
            extracted_path_to_use = input_path
        else:
            print(f"Error: Input path '{input_path}' is not a valid ZIP file or directory.")
            sys.exit(1)

        print(f"Building CKG for: {extracted_path_to_use}")
        ckg_instance = build_ckg_from_path(extracted_path_to_use)

        if not ckg_instance or len(ckg_instance) == 0:
             print("CKG build resulted in an empty graph. Exiting.")
             sys.exit(0) 

        print(f"Resolving CKG edges...")
        resolve_ckg_edges(ckg_instance) 

        print(f"CKG contains {len(ckg_instance)} nodes.")

        visualize_matplotlib(ckg_instance.graph, output_file="ckg_visualization.png")
        export_ckg_to_json(ckg_instance.graph, output_file="ckg_data.json")

    except Exception as e:
        print(f"An error occurred during the visualization/export process: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if temp_dir_context_manager:
             print(f"Temporary directory '{temp_dir_context_manager.name}' will be cleaned up.")