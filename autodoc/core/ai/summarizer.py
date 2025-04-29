import asyncio
import logging
import time
from typing import List, Dict, Optional, Tuple, Coroutine, Any
from uuid import UUID

from ..ckg.graph import CKG
from ...models.graph import (
    BaseNode, FunctionNode, ClassNode, FileNode, FolderNode, NonFunctionNonClassNode
)
from ...models.settings import Settings 
from ...services.llm_service import GroqLLMService 
from . import prompts 

logger = logging.getLogger(__name__)

LLM_CONCURRENCY = 5 
FAIL_ON_LLM_ERROR = False 

class LLMException(Exception):
    """Custom exception for LLM related errors."""
    pass

def _get_function_context(ckg: CKG, node: FunctionNode) -> Dict[str, Any]:
    """Gathers context specifically for a FunctionNode."""
    context = {
        "signature": node.signature,
        "docstring": node.docstring,
        "code_snippet": node.code_snippet,
        "file_path": node.file_path,
        "is_method": node.is_method,
        "class_name": None,
        "access_modifier": node.access_modifier,
        "callers": [],
        "callees": [],
        "imports_used": []
    }
    if node.is_method and node.belongs_to:
        parent_class = ckg.get_node(node.belongs_to)
        if parent_class and isinstance(parent_class, ClassNode):
            context["class_name"] = parent_class.name

    for pred_node in ckg.get_predecessors(node.id, edge_type="CALLS"):
         caller_desc = f"`{pred_node.name}` ({pred_node.node_type} in `{pred_node.file_path}`)"
         context["callers"].append(caller_desc)

    for succ_node in ckg.get_successors(node.id, edge_type="CALLS"):
         callee_desc = f"`{succ_node.name}` ({succ_node.node_type})"
         context["callees"].append(callee_desc)

    for target_node in ckg.get_successors(node.id, edge_type="USES_IMPORT"):
         if isinstance(target_node, FileNode) and target_node.module_path:
             context["imports_used"].append(f"`{target_node.module_path}`")
         elif isinstance(target_node, FileNode):
              context["imports_used"].append(f"(File: `{target_node.name}`)")


    return context

def _get_class_context(ckg: CKG, node: ClassNode) -> Dict[str, Any]:
    """Gathers context specifically for a ClassNode."""
    context = {
        "class_name": node.name,
        "signature": node.signature, 
        "docstring": node.docstring,
        "code_snippet": node.code_snippet,
        "file_path": node.file_path,
        "access_modifier": node.access_modifier,
        "inherits_from": [],
        "methods": [],
        "imports_used": [] 
    }
    for parent_node in ckg.get_successors(node.id, edge_type="INHERITS_FROM"):
        if isinstance(parent_node, ClassNode):
            context["inherits_from"].append(f"`{parent_node.name}`")

    for child_node in ckg.get_successors(node.id, edge_type="CONTAINS"):
        if isinstance(child_node, FunctionNode) and child_node.is_method:
            method_desc = child_node.signature if child_node.signature else child_node.name
            context["methods"].append(f"`{method_desc}`")

    return context

def _get_non_func_class_context(ckg: CKG, node: NonFunctionNonClassNode) -> Dict[str, Any]:
    """Gathers context specifically for a NonFunctionNonClassNode."""
    context = {
        "name": node.name,
        "code_snippet": node.code_snippet,
        "line_numbers": (node.start_line, node.end_line),
        "file_path": node.file_path,
        "calls_made": [],
        "imports_used": []
    }
    for succ_node in ckg.get_successors(node.id, edge_type="CALLS"):
         callee_desc = f"`{succ_node.name}` ({succ_node.node_type})"
         context["calls_made"].append(callee_desc)

    for target_node in ckg.get_successors(node.id, edge_type="USES_IMPORT"):
         if isinstance(target_node, FileNode) and target_node.module_path:
             context["imports_used"].append(f"`{target_node.module_path}`")
         elif isinstance(target_node, FileNode):
              context["imports_used"].append(f"(File: `{target_node.name}`)")

    return context

def _get_file_context(ckg: CKG, node: FileNode) -> Dict[str, Any]:
    """Gathers context specifically for a FileNode."""
    context = {
        "file_path": node.file_path,
        "module_path": node.module_path,
        "contained_classes": [],
        "contained_functions": [],
        "contained_blocks_count": 0,
        "imports_made": [],
        "component_summaries": {}
    }
    for child_node in ckg.get_successors(node.id, edge_type="CONTAINS"):
        summary_key = f"{child_node.node_type}: {child_node.name}"
        summary = child_node.summary
        if summary and not summary.startswith("(Summary generation failed") and not summary.startswith("(Error"):
             context["component_summaries"][summary_key] = summary
        else: logger.debug(f"Skipping summary for {summary_key} in context for {node.name}")


        if isinstance(child_node, ClassNode):
            context["contained_classes"].append(f"`{child_node.name}`")
        elif isinstance(child_node, FunctionNode):
            context["contained_functions"].append(f"`{child_node.name}`")
        elif isinstance(child_node, NonFunctionNonClassNode):
             context["contained_blocks_count"] += 1

    for target_node in ckg.get_successors(node.id, edge_type="IMPORTS"):
        if isinstance(target_node, FileNode) and target_node.module_path:
             context["imports_made"].append(f"`{target_node.module_path}`")
        elif isinstance(target_node, FileNode):
             context["imports_made"].append(f"(File: `{target_node.name}`)")

    return context

def _get_folder_context(ckg: CKG, node: FolderNode) -> Dict[str, Any]:
    """Gathers context specifically for a FolderNode."""
    context = {
        "folder_path": node.file_path,
        "contained_files": [],
        "contained_folders": [],
        "component_summaries": {}
    }
    for child_node in ckg.get_successors(node.id, edge_type="CONTAINS"):
        summary_key = f"{child_node.node_type}: {child_node.name}"
        summary = child_node.summary
        if summary and not summary.startswith("(Summary generation failed") and not summary.startswith("(Error"):
            context["component_summaries"][summary_key] = summary
        else: logger.debug(f"Skipping summary for {summary_key} in context for {node.name}")

        if isinstance(child_node, FileNode):
            context["contained_files"].append(f"`{child_node.name}`")
        elif isinstance(child_node, FolderNode):
            context["contained_folders"].append(f"`{child_node.name}`")

    return context
\

async def _summarize_node_task(
    ckg: CKG,
    node_id: UUID,
    llm_service: GroqLLMService,
    semaphore: asyncio.Semaphore
) -> Tuple[UUID, Optional[str]]:
    """
    Async task wrapper to acquire semaphore, gather context, generate prompt,
    call LLM, and return summary for one node.
    """
    node = ckg.get_node(node_id)
    if not node:
        logger.error(f"Node with ID {node_id} not found during summarization task.")
        return node_id, "(Error: Node not found)"

    if node.summary is not None and node.summary != "(Summary generation failed)":
        logger.debug(f"Node {node.id} ('{node.name}') already summarized. Skipping task.")
        return node_id, node.summary

    async with semaphore: 
        logger.debug(f"Acquired semaphore for summarizing node {node.id} ('{node.name}')")
        prompt = ""
        summary = None
        error_message = None
        try:
            context: Dict[str, Any] = {}
            if isinstance(node, FunctionNode):
                context = _get_function_context(ckg, node)
                prompt = prompts.generate_function_prompt(**context)
            elif isinstance(node, ClassNode):
                context = _get_class_context(ckg, node)
                prompt = prompts.generate_class_prompt(**context)
            elif isinstance(node, NonFunctionNonClassNode):
                 context = _get_non_func_class_context(ckg, node)
                 prompt = prompts.generate_non_function_non_class_prompt(**context)
            elif isinstance(node, FileNode):
                context = _get_file_context(ckg, node)
                prompt = prompts.generate_file_prompt(**context)
            elif isinstance(node, FolderNode):
                context = _get_folder_context(ckg, node)
                prompt = prompts.generate_folder_prompt(**context)
            else:
                logger.warning(f"Summarization not implemented for node type: {node.node_type} (Node ID: {node_id})")
                error_message = "(Error: Unknown node type for summarization)"

            if prompt:
                logger.debug(f"Generating summary for {node.node_type} node: {node.name} (ID: {node_id})")
                summary = await llm_service.generate_summary(prompt) 
                logger.debug(f"Received summary for node {node_id}: {summary[:100] if summary else 'None'}...")
                if summary is None:
                     error_message = "(Summary generation failed)" 
                else:
                     summary = summary.strip().replace("```", "`")

            return node_id, summary if error_message is None else error_message

        except Exception as e:
            logger.error(f"Unexpected error summarizing node {node.node_type} {node.name} (ID: {node_id}): {e}", exc_info=True)
            if FAIL_ON_LLM_ERROR:
                 raise LLMException(f"Failed summarizing node {node_id}: {e}") from e
            return node_id, f"(Error: {type(e).__name__} during summarization)"
        finally:
             logger.debug(f"Released semaphore for node {node.id}")


async def generate_summaries(ckg: CKG, settings: Settings):
    """
    Orchestrates the bottom-up summarization of all nodes in the CKG.

    Iterates through nodes from maximum depth upwards, generating summaries
    concurrently for each depth level. Modifies the CKG nodes in place by
    setting the 'summary' attribute.

    Args:
        ckg: The fully resolved Code Knowledge Graph instance.
        llm_service: An instance of the LLM service client (e.g., LLMService).
    """
    if not ckg or len(ckg) == 0:
        logger.warning("CKG is empty. Skipping summarization.")
        return

    max_depth = ckg.max_depth
    concurrency = getattr(settings, 'llm_concurrency', LLM_CONCURRENCY)
    logger.info(f"Starting bottom-up summarization. Max depth: {max_depth}. Concurrency: {concurrency}.")
    start_time_total = time.time()

    try:
        llm_service = GroqLLMService()
    except Exception as e:
        logger.critical(f"Failed to initialize LLM Service: {e}. Aborting summarization.")
        for node in ckg.get_all_nodes():
           if node.summary is None: 
               node.summary = "(LLM Service Initialization Failed)"
        return

    semaphore = asyncio.Semaphore(concurrency)

    total_nodes_processed = 0
    total_nodes_failed = 0

    for depth in range(max_depth, -1, -1):
        start_time_depth = time.time()
        nodes_at_depth = list(ckg.find_nodes(depth=depth))

        if not nodes_at_depth:
            logger.debug(f"No nodes found at depth {depth}.")
            continue

        logger.info(f"Processing {len(nodes_at_depth)} nodes at depth {depth}...")

        tasks: List[Coroutine] = []
        node_ids_at_depth = [node.id for node in nodes_at_depth]
        for node_id in node_ids_at_depth:
            tasks.append(_summarize_node_task(ckg, node_id, llm_service, semaphore))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        summarized_count = 0
        failed_count = 0
        for i, result in enumerate(results):
            node_id = node_ids_at_depth[i] 
            node = ckg.get_node(node_id)

            if isinstance(result, Exception):
                 logger.error(f"Summarization task for node {node_id} failed with exception: {result}", exc_info=False)
                 failed_count += 1
                 if node and node.summary is None: 
                     node.summary = f"(Error: Task failed - {type(result).__name__})"
            elif result is None:
                 logger.error(f"Summarization task for node {node_id} returned None unexpectedly.")
                 failed_count += 1
                 if node and node.summary is None:
                     node.summary = "(Error: Task returned None)"
            else:
                 _, summary = result
                 if node:
                     node.summary = summary 
                     if summary is None or summary.startswith("(Summary generation failed") or summary.startswith("(Error"):
                         failed_count += 1
                         logger.warning(f"Failed to generate summary for node {node_id} ('{node.name}'). Reason: {summary}")
                     else:
                         summarized_count += 1
                 else:
                      logger.error(f"Node {node_id} not found when processing results for depth {depth}.")
                      failed_count +=1


        total_nodes_processed += len(nodes_at_depth)
        total_nodes_failed += failed_count
        elapsed_depth = time.time() - start_time_depth
        logger.info(f"Finished processing depth {depth} in {elapsed_depth:.2f}s. Summarized: {summarized_count}, Failed/Skipped: {failed_count}")

    await generate_final_overview(ckg, llm_service, semaphore)

    elapsed_total = time.time() - start_time_total
    logger.info(f"CKG summarization complete in {elapsed_total:.2f} seconds. Total nodes processed: {total_nodes_processed}, Total failures: {total_nodes_failed}.")


async def generate_final_overview(ckg: CKG, llm_service: GroqLLMService, semaphore: asyncio.Semaphore) -> Optional[str]:
    """Generates the final project overview summary."""
    logger.info("Generating final project overview...")
    root_nodes = list(ckg.find_nodes(depth=0))
    if not root_nodes:
         logger.error("Could not find any root nodes at depth 0 for overview.")
         return None

    root_node = root_nodes[0]
    root_folder_name = root_node.name

    component_summaries = {}
    for r_node in root_nodes:
        for child_node in ckg.get_successors(r_node.id, edge_type="CONTAINS"):
            summary_key = f"{child_node.node_type}: {child_node.name}"
            summary = child_node.summary
            if summary and not summary.startswith("(Summary generation failed") and not summary.startswith("(Error"):
                component_summaries[summary_key] = summary

    if not component_summaries:
         logger.warning("No summaries found for top-level components. Cannot generate overview.")
         return None

    async with semaphore: 
        try:
            prompt = prompts.generate_project_overview_prompt(
                root_folder_name=root_folder_name, 
                component_summaries=component_summaries
            )
            overview = await llm_service.generate_summary(prompt)
            if overview:
                overview = overview.strip().replace("```", "`")
                logger.info("Successfully generated project overview.")
                return overview
            else:
                logger.error("Failed to generate project overview (LLM returned None).")
                return None
        except Exception as e:
            logger.error(f"Failed to generate project overview: {e}", exc_info=True)
            return None