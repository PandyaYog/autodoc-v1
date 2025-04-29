import logging
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

LLM_ROLE = "You are an expert technical writer specializing in analyzing Python code and generating concise, accurate documentation based *only* on the provided information. Do not infer or invent functionality."


def _format_list(items: Optional[List[str]], default: str = "N/A") -> str:
    """Formats a list into a bulleted string or returns a default."""
    if not items:
        return default
    return "\n".join(f"  - {item}" for item in items)

def _format_code(code: Optional[str], language: str = "python") -> str:
    """Formats code into a Markdown code block."""
    if not code:
        return "  N/A" 
    return f"```python\n{code.strip()}\n```"


def generate_function_prompt(
    signature: Optional[str],
    docstring: Optional[str],
    code_snippet: Optional[str],
    file_path: str,
    is_method: bool,
    class_name: Optional[str],
    access_modifier: Optional[str],
    callers: Optional[List[str]],
    callees: Optional[List[str]],
    imports_used: Optional[List[str]] 
) -> str:
    """Generates the prompt for summarizing a function or method."""

    context_parts = [
        f"- **File Path:** `{file_path}`"
    ]
    if is_method and class_name:
        context_parts.append(f"- **Parent Class:** `{class_name}`")
    if access_modifier:
         context_parts.append(f"- **Access:** `{access_modifier}`")

    context_parts.append(f"- **Called By:**\n{_format_list(callers, default='  - Not specified or top-level entry.')}")
    context_parts.append(f"- **Calls:**\n{_format_list(callees, default='  - None specified.')}")
    context_parts.append(f"- **Imports Used:**\n{_format_list(imports_used, default='  - None specified.')}") 

    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the following Python {'method' if is_method else 'function'}.

**Input Data:**
- **Signature:**
{_format_code(signature)}
- **Docstring:**
{_format_code(docstring, language='') if docstring else '  N/A'}
- **Code Snippet:**
{_format_code(code_snippet)}

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the primary purpose of this {'method' if is_method else 'function'}.
2.  Briefly describe its parameters and return value (if discernible from signature/docstring).
3.  Mention any key operations or logic evident from the code snippet or docstring.
4.  Note its relationships (who calls it, what it calls, imports used) based *only* on the provided context.
5.  Output *only* the Markdown summary, without preamble or explanation.
6.  **Strictly adhere to the provided information. Do not add details not present in the input or context.** If information is missing, state that clearly or omit the detail.
"""
    return prompt.strip()


def generate_class_prompt(
    class_name: str,
    signature: Optional[str],
    docstring: Optional[str],
    code_snippet: Optional[str],
    file_path: str,
    access_modifier: Optional[str],
    inherits_from: Optional[List[str]],
    methods: Optional[List[str]],
    imports_used: Optional[List[str]] 
) -> str:
    """Generates the prompt for summarizing a class."""

    context_parts = [
        f"- **File Path:** `{file_path}`",
        f"- **Access:** `{access_modifier or 'public'}`",
        f"- **Inherits From:**\n{_format_list(inherits_from, default='  - None (or object)')}",
        f"- **Key Methods Defined:**\n{_format_list(methods, default='  - None specified.')}",
        f"- **Imports Used:**\n{_format_list(imports_used, default='  - None specified.')}"
    ]
    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the Python class `{class_name}`.

**Input Data:**
- **Class Definition:** `{signature or class_name}`
- **Docstring:**
{_format_code(docstring, language='') if docstring else '  N/A'}
- **Code Snippet (Definition):**
{_format_code(code_snippet)}

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the primary purpose or role of this class.
2.  Mention its key characteristics based on inheritance and contained methods.
3.  Describe its relationship to parent classes (if any).
4.  Output *only* the Markdown summary, without preamble or explanation.
5.  **Strictly adhere to the provided information. Do not add details not present in the input or context.** If information is missing, state that clearly or omit the detail.
"""
    return prompt.strip()


def generate_non_function_non_class_prompt(
    name: str,
    code_snippet: Optional[str],
    line_numbers: Tuple[Optional[int], Optional[int]],
    file_path: str,
    calls_made: Optional[List[str]],
    imports_used: Optional[List[str]] 
) -> str:
    """Generates the prompt for summarizing a top-level code block."""

    context_parts = [
        f"- **File Path:** `{file_path}`",
        f"- **Line Range:** {line_numbers[0]}-{line_numbers[1]}",
        f"- **Calls Made:**\n{_format_list(calls_made, default='  - None specified.')}",
        f"- **Imports Used:**\n{_format_list(imports_used, default='  - None specified.')}"
    ]
    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the top-level Python code block named `{name}`.

**Input Data:**
- **Code Snippet:**
{_format_code(code_snippet)}

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Describe the purpose of this code block (e.g., setup, configuration, global definitions, script execution).
2.  Mention any significant actions like function calls or dependencies on imports based *only* on the provided context.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Strictly adhere to the provided information. Do not add details not present in the input or context.**
"""
    return prompt.strip()


def generate_file_prompt(
    file_path: str,
    module_path: Optional[str],
    contained_classes: Optional[List[str]],
    contained_functions: Optional[List[str]],
    contained_blocks_count: int,
    imports_made: Optional[List[str]],
    component_summaries: Dict[str, str] 
) -> str:
    """Generates the prompt for summarizing a file."""

    summary_lines = []
    for name, summary in component_summaries.items():
        indented_summary = "\n".join(f"    {line}" for line in summary.strip().splitlines())
        summary_lines.append(f"  - **{name}:**\n{indented_summary}")
    summary_str = "\n".join(summary_lines) if summary_lines else "  N/A"

    context_parts = [
        f"- **Module Path:** `{module_path or 'N/A'}`",
        f"- **Contained Classes:** {_format_list(contained_classes, default='  - None')}",
        f"- **Contained Functions:** {_format_list(contained_functions, default='  - None')}",
        f"- **Contained Top-Level Blocks:** {contained_blocks_count}", 
        f"- **Imports Made:**\n{_format_list(imports_made, default='  - None specified.')}",
        f"- **Summaries of Contained Components:**\n{summary_str}" 
    ]
    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the Python file `{file_path}`.

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the overall purpose and role of this file within the project.
2.  Base the summary on the provided list of contained components (classes, functions, blocks) and their individual summaries.
3.  Mention key dependencies based on the 'Imports Made'.
4.  Output *only* the Markdown summary, without preamble or explanation.
5.  **Strictly adhere to the provided information. Synthesize the summary from the component summaries and file context only.** Do not invent functionality or relationships.
"""
    return prompt.strip()


def generate_folder_prompt(
    folder_path: str,
    contained_files: Optional[List[str]],
    contained_folders: Optional[List[str]],
    component_summaries: Dict[str, str] 
) -> str:
    """Generates the prompt for summarizing a folder."""

    summary_lines = []
    for name, summary in component_summaries.items():
        indented_summary = "\n".join(f"    {line}" for line in summary.strip().splitlines())
        summary_lines.append(f"  - **{name}:**\n{indented_summary}")
    summary_str = "\n".join(summary_lines) if summary_lines else "  N/A"


    context_parts = [
        f"- **Contained Files:** {_format_list(contained_files, default='  - None')}",
        f"- **Contained Subfolders:** {_format_list(contained_folders, default='  - None')}",
        f"- **Summaries of Contained Components:**\n{summary_str}"
    ]
    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the folder `{folder_path}`.

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the overall purpose and role of this folder (potentially a package or sub-package).
2.  Base the summary on the provided list of contained files and subfolders and their individual summaries.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Strictly adhere to the provided information. Synthesize the summary from the component summaries and folder context only.** Do not invent functionality or structure.
"""
    return prompt.strip()


def generate_project_overview_prompt(
    root_folder_name: str,
    component_summaries: Dict[str, str] 
) -> str:
    """Generates the prompt for the overall project overview."""

    summary_lines = []
    for name, summary in component_summaries.items():
        indented_summary = "\n".join(f"    {line}" for line in summary.strip().splitlines())
        summary_lines.append(f"  - **{name}:**\n{indented_summary}")
    summary_str = "\n".join(summary_lines) if summary_lines else "  N/A"

    context_parts = [
        f"- **Summaries of Top-Level Components:**\n{summary_str}" 
    ]
    context_str = "\n".join(context_parts)

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a high-level Markdown overview for the Python project contained in the root folder `{root_folder_name}`.

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Provide a brief, high-level summary of the project's likely purpose and structure.
2.  Base the overview *entirely* on the provided summaries of the top-level files and folders.
3.  Focus on the main functional areas suggested by the component summaries.
4.  Output *only* the Markdown overview, without preamble or explanation.
5.  **Strictly adhere to the provided information. Synthesize the overview from the component summaries only.** Do not speculate or add external knowledge.
"""
    return prompt.strip()