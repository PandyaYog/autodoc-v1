import logging
from typing import List, Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

LLM_ROLE = (
    "You are an expert technical writer specializing in analyzing source code, "
    "configuration files, and web assets. You generate concise, accurate documentation "
    "based *only* on the provided information. Do not infer or invent functionality."
)


def _format_list(items: Optional[List[str]], default: str = "N/A") -> str:
    """Formats a list into a bulleted string or returns a default."""
    if not items:
        return default
    return "\n".join(f"  - {item}" for item in items)

def _format_code(code: Optional[str], language: str = "python") -> str:
    """Formats code into a Markdown code block with the specified language identifier."""
    if not code:
        return "  N/A"
    return f"```{language}\n{code.strip()}\n```"


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
2.  Mention any significant actions like function calls or import statements:
    - Prefer the **CKG context** (`Calls Made`, `Imports Used`) if those lists are populated.
    - If those lists show "None specified" but the **code snippet** visibly contains function calls or import statements, describe them directly from the code snippet.
    - **Never write "no function calls or imports are specified" if the code snippet clearly shows them.**
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **The code snippet is the primary source of truth.** When CKG context is absent for calls/imports, derive the information from the code snippet directly rather than claiming the information is missing.
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

def generate_import_block_prompt(
    file_path: str,
    imports: List[Dict[str, Any]],
    line_numbers: Tuple[Optional[int], Optional[int]],
) -> str:
    """Generates the prompt for summarizing an ImportBlockNode."""

    # Collect raw code snippets. Multiple import entries may share the same
    # code_snippet (one entry per alias in `from x import a, b, c`) — deduplicate
    # while preserving insertion order so the displayed block matches the source.
    seen: dict = {}
    for imp in imports:
        code = imp.get("code_snippet")
        if code and code.strip():
            seen[code.strip()] = None          # dict preserves insertion order
        else:
            # Fallback: reconstruct the line from structured fields
            if imp["type"] == "import":
                line = f"import {imp['name']}"
                if imp.get("alias"):
                    line += f" as {imp['alias']}"
            else:
                level_dots = "." * imp.get("level", 0)
                module_part = imp.get("module", "")
                name_part = imp["name"]
                if imp.get("alias"):
                    name_part += f" as {imp['alias']}"
                line = f"from {level_dots}{module_part} import {name_part}"
            seen[line] = None

    import_block_str = "\n".join(seen.keys())

    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the block of import statements found in the file `{file_path}` between lines {line_numbers[0]}-{line_numbers[1]}.

**Input Data:**
- **Import Statements:**
{_format_code(import_block_str)}

**Instructions:**
1.  Briefly describe the purpose of this block (i.e., importing dependencies).
2.  List the primary libraries or modules being imported (e.g., "Imports standard libraries like os, typing, and third-party libraries like fastapi, pydantic.").
3.  Mention any significant relative imports if present (e.g., "...and internal project modules like .config, .models").
4.  Output *only* the Markdown summary, without preamble or explanation.
5.  **Focus only on the import statements provided.** Do not infer functionality beyond importing.
"""
    return prompt.strip()


def generate_react_component_prompt(
    name: str,
    docstring: Optional[str],
    code_snippet: Optional[str],
    file_path: str,
    props: Optional[List[str]],
    hooks_used: Optional[List[str]],
    renders_components: Optional[List[str]],
    callers: Optional[List[str]]
) -> str:
    """Generates the prompt for summarizing a React component."""
    
    context_parts = [
        f"- **File Path:** `{file_path}`",
        f"- **Props Expected:**\n{_format_list(props, default='  - None specified or inferred.')}",
        f"- **Hooks Used (State/Effects):**\n{_format_list(hooks_used, default='  - None specified.')}",
        f"- **Renders Components:**\n{_format_list(renders_components, default='  - None specified.')}",
        f"- **Rendered By (Callers):**\n{_format_list(callers, default='  - Not specified or top-level component.')}"
    ]
    context_str = "\n".join(context_parts)
    
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the React component `{name}`.

**Input Data:**
- **Docstring:**
{_format_code(docstring, language='') if docstring else '  N/A'}
- **Code Snippet:**
{_format_code(code_snippet, language='javascript')}

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the primary UI functionality and purpose of this React component.
2.  Briefly describe the props it accepts and the internal state/side effects it manages (via hooks).
3.  Mention what key sub-components it renders to build the UI, and where it is used (Rendered By).
4.  Output *only* the Markdown summary, without preamble or explanation.
5.  **Strictly adhere to the provided information. Do not add details not present in the input or context. Specifically, DO NOT hallucinate or guess about visual styles, CSS classes, colors, or visual layouts unless explicitly written in the code snippet.**
"""
    return prompt.strip()

def generate_react_hook_prompt(
    name: str,
    signature: Optional[str],
    docstring: Optional[str],
    code_snippet: Optional[str],
    file_path: str,
    callers: Optional[List[str]],
    callees: Optional[List[str]]
) -> str:
    """Generates the prompt for summarizing a custom React hook."""
    
    context_parts = [
        f"- **File Path:** `{file_path}`",
        f"- **Used By (Callers):**\n{_format_list(callers, default='  - Not specified.')}",
        f"- **Calls (Other Hooks/Functions):**\n{_format_list(callees, default='  - None specified.')}"
    ]
    context_str = "\n".join(context_parts)
    
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the custom React hook `{name}`.

**Input Data:**
- **Signature:**
{_format_code(signature, language='javascript')}
- **Docstring:**
{_format_code(docstring, language='') if docstring else '  N/A'}
- **Code Snippet:**
{_format_code(code_snippet, language='javascript')}

**Context from Code Knowledge Graph:**
{context_str}

**Instructions:**
1.  Summarize the primary purpose of this custom hook (e.g., state management, data fetching, side effects).
2.  Briefly describe its inputs (parameters) and what it returns based on the signature/snippet.
3.  Note where it is used and what other hooks/functions it calls.
4.  Output *only* the Markdown summary, without preamble or explanation.
5.  **Strictly adhere to the provided information. Do not add details not present in the input or context.**
"""
    return prompt.strip()

# ---------------------------------------------------------------------------
# Non-Python file prompts
# ---------------------------------------------------------------------------

def generate_markdown_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a Markdown file (.md, .rst)."""
    content_block = _format_code(raw_content, language='markdown') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the documentation file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Summarize what this document covers and its purpose within the project.
2.  Highlight key sections, features, or instructions described.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Base the summary strictly on the provided content.**
"""
    return prompt.strip()


def generate_text_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a plain-text file (.txt, .rst)."""
    content_block = _format_code(raw_content, language='') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the text file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Describe the purpose of this file (e.g., dependency list, changelog, license, notes).
2.  Highlight any important entries or information.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Base the summary strictly on the provided content.**
"""
    return prompt.strip()


def generate_yaml_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a YAML config file (.yaml, .yml)."""
    content_block = _format_code(raw_content, language='yaml') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the YAML configuration file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Identify what this YAML file configures (e.g., CI/CD pipeline, Docker Compose services, application settings, linting rules).
2.  Summarize the key sections, services, or settings defined.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Base the summary strictly on the provided content.**
"""
    return prompt.strip()


def generate_toml_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a TOML config file (.toml)."""
    content_block = _format_code(raw_content, language='toml') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the TOML configuration file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Identify what this TOML file configures (e.g., project metadata, build system, tool settings in pyproject.toml).
2.  Highlight key sections such as dependencies, scripts, or tool configurations.
3.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Base the summary strictly on the provided content.**
"""
    return prompt.strip()


def generate_dockerfile_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a Dockerfile."""
    content_block = _format_code(raw_content, language='dockerfile') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the Dockerfile `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Describe the base image used and what environment is being built.
2.  Summarize the key build steps (dependencies installed, files copied, commands run).
3.  Mention the exposed ports and the default startup command if present.
4.  Output *only* the Markdown summary, without preamble or explanation.
4.  **Base the summary strictly on the provided content.**
"""
    return prompt.strip()


def generate_json_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a JSON data or configuration file."""
    content_block = _format_code(raw_content, language='json') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the JSON file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Identify the purpose of this JSON file (e.g., package manifest, API response schema,
    application configuration, i18n translations, data fixture, tsconfig, eslint config).
2.  Summarize the top-level keys and what they configure or represent.
3.  If it is a `package.json`, highlight: project name/version, main scripts, key
    dependencies, and devDependencies.
4.  If it is a `tsconfig.json` or `jsconfig.json`, describe the key compiler options set
    (e.g., target, module, strict mode, path aliases).
5.  Output *only* the Markdown summary, without preamble or explanation.
6.  **Base the summary strictly on the provided content.** Do not invent fields or values.
"""
    return prompt.strip()


def generate_html_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing an HTML file."""
    content_block = _format_code(raw_content, language='html') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the HTML file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Describe the purpose of this HTML file (e.g., SPA entry point, email template,
    static page, server-rendered template).
2.  Note the key structural elements present in the `<head>`: title, charset, viewport
    meta tags, linked stylesheets, and injected scripts.
3.  Identify root mounting points (e.g., `<div id="root">`) and any inline scripts or
    special data attributes.
4.  If it references external resources (CDN links, bundled assets), mention them.
5.  Output *only* the Markdown summary, without preamble or explanation.
6.  **Base the summary strictly on the provided content.** Do not speculate about the
    JavaScript framework or application behavior beyond what the HTML markup reveals.
"""
    return prompt.strip()


def generate_css_file_prompt(file_path: str, raw_content: Optional[str]) -> str:
    """Generates the prompt for summarizing a CSS stylesheet."""
    content_block = _format_code(raw_content, language='css') if raw_content else "  N/A"
    prompt = f"""
{LLM_ROLE}

**Task:** Generate a concise Markdown summary for the CSS file `{file_path}`.

**File Contents:**
{content_block}

**Instructions:**
1.  Describe what UI elements or sections this stylesheet is responsible for styling
    (e.g., global reset, typography, a specific component, a page layout).
2.  Note the key design patterns or features used:
    - CSS custom properties / design tokens (e.g., `--color-primary`, `--spacing-md`)
    - Media queries and the responsive breakpoints they define
    - Keyframe animations and transitions
    - Layout strategies (CSS Grid, Flexbox)
3.  If the file is a global stylesheet (e.g., `index.css`, `App.css`, `global.css`),
    describe the reset/normalize rules, typography defaults, and color tokens it defines.
4.  If it is a component stylesheet, identify which component it belongs to and what
    interactive states or variants it styles (e.g., hover, active, disabled, open).
5.  Output *only* the Markdown summary, without preamble or explanation.
6.  **Strictly describe structural and logical CSS patterns only.** Do NOT enumerate
    individual color hex values, pixel measurements, or exhaustive property lists —
    focus on design intent and architectural patterns.
"""
    return prompt.strip()