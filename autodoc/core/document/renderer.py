"""
Document Renderer — converts assembled Markdown documentation to a styled PDF.

Pipeline:
  Markdown string (from DocumentAssembler)
      → HTML body   (via `markdown` library, with fenced_code + tables extensions)
      → Full HTML   (body injected into a styled HTML/CSS template)
      → PDF bytes   (via weasyprint)

The CSS template is modelled after a professional technical documentation style:
  - Gradient cover header with project name
  - Heading hierarchy: h2 (root) → h6 (code blocks), each visually distinct
  - Dark-background code blocks with monospace font
  - Metadata boxes (paths, signatures) with subtle borders
  - A4 page size with running page numbers in the footer
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ── CSS template ──────────────────────────────────────────────────────────────

_CSS = """
@page {
    size: A4;
    margin: 22mm 16mm 22mm 16mm;
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
        font-size: 8.5pt;
        color: #94a3b8;
    }
    @bottom-left {
        content: string(doc-title);
        font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
        font-size: 8.5pt;
        color: #94a3b8;
    }
}

*, *::before, *::after {
    box-sizing: border-box;
}

body {
    font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.65;
    color: #1e293b;
    margin: 0;
    padding: 0;
    background-color: #ffffff;
}

/* ── Cover header ── */
.doc-header {
    margin: -22mm -16mm 28px -16mm;
    padding: 32px 16mm 28px 16mm;
    background: linear-gradient(135deg, #1e3a8a 0%, #0d9488 100%);
    color: #ffffff;
    string-set: doc-title content();
}

.doc-header h1 {
    margin: 0 0 6px 0;
    font-size: 20pt;
    font-weight: 700;
    letter-spacing: -0.3px;
    color: #ffffff;
    border: none;
    page-break-after: avoid;
}

.doc-header .subtitle {
    font-size: 10.5pt;
    color: #ccfbf1;
    margin: 0;
    font-weight: 300;
    opacity: 0.9;
}

/* ── Headings ── */
/* h2 = root folder/file */
h2 {
    font-size: 15pt;
    color: #1e3a8a;
    border-left: 4px solid #0d9488;
    padding-left: 10px;
    margin-top: 32px;
    margin-bottom: 14px;
    page-break-after: avoid;
}

/* h3 = sub-folder / file inside root */
h3 {
    font-size: 13pt;
    color: #0f172a;
    border-bottom: 1.5px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 26px;
    margin-bottom: 12px;
    page-break-after: avoid;
}

/* h4 = file inside sub-folder / class */
h4 {
    font-size: 11.5pt;
    color: #1e40af;
    margin-top: 22px;
    margin-bottom: 10px;
    page-break-after: avoid;
}

/* h5 = function / method at file level */
h5 {
    font-size: 10.5pt;
    color: #334155;
    margin-top: 18px;
    margin-bottom: 8px;
    page-break-after: avoid;
}

/* h6 = import block / code block / nested element */
h6 {
    font-size: 9.5pt;
    color: #0d9488;
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-top: 14px;
    margin-bottom: 6px;
    page-break-after: avoid;
}

/* ── Body text ── */
p {
    margin-top: 0;
    margin-bottom: 10px;
}

ul, ol {
    margin-top: 0;
    margin-bottom: 10px;
    padding-left: 22px;
}

li {
    margin-bottom: 4px;
}

/* ── Code blocks ── */
pre {
    background-color: #1e293b;
    color: #f1f5f9;
    padding: 12px 14px;
    border-radius: 6px;
    font-family: 'Consolas', 'Courier New', Courier, monospace;
    font-size: 8.5pt;
    margin-top: 8px;
    margin-bottom: 14px;
    line-height: 1.45;
    white-space: pre-wrap;
    word-break: break-all;
    page-break-inside: avoid;
}

code {
    font-family: 'Consolas', 'Courier New', Courier, monospace;
    font-size: 9pt;
    background-color: #f1f5f9;
    color: #0f172a;
    padding: 1px 5px;
    border-radius: 3px;
}

pre code {
    background-color: transparent;
    color: inherit;
    padding: 0;
    border-radius: 0;
    font-size: inherit;
}

/* ── Blockquotes (used for meta info like Path/Signature) ── */
blockquote {
    background-color: #f8fafc;
    border-left: 3px solid #cbd5e1;
    border-radius: 0 6px 6px 0;
    margin: 8px 0 14px 0;
    padding: 8px 12px;
    font-size: 9.5pt;
    color: #475569;
}

blockquote p {
    margin: 0;
}

/* ── Tables ── */
table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 14px;
    font-size: 9.5pt;
}

th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 600;
    padding: 6px 10px;
    border: 1px solid #e2e8f0;
    text-align: left;
}

td {
    padding: 5px 10px;
    border: 1px solid #e2e8f0;
    color: #1e293b;
    vertical-align: top;
}

tr:nth-child(even) td {
    background-color: #f8fafc;
}

/* ── Horizontal rule (used as section separator) ── */
hr {
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 20px 0;
}

/* ── Details / summary (rendered as styled box by weasyprint) ── */
details {
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    margin: 10px 0 14px 0;
    padding: 0;
    page-break-inside: avoid;
}

summary {
    background-color: #f8fafc;
    padding: 6px 12px;
    font-size: 9pt;
    font-weight: 600;
    color: #64748b;
    cursor: pointer;
    border-radius: 6px 6px 0 0;
    border-bottom: 1px solid #e2e8f0;
}

details > *:not(summary) {
    padding: 10px 12px 4px 12px;
}

/* ── Strong/em ── */
strong {
    color: #0f172a;
    font-weight: 600;
}

em {
    color: #475569;
}
"""


# ── HTML page template ────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>{css}</style>
</head>
<body>
    <div class="doc-header">
        <h1>{title}</h1>
        <div class="subtitle">Technical Codebase Documentation &mdash; Auto-generated by AutoDoc AI</div>
    </div>
    {body}
</body>
</html>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def _extract_project_title(markdown_content: str) -> str:
    """
    Extracts a clean project title from the first heading in the Markdown.

    The assembler's root heading looks like:
        ## Folder: my-project.zip
    We strip the 'Folder: ' / 'File: ' prefix and the '.zip' extension if present.
    """
    match = re.search(r"^#{1,6}\s+(?:Folder:|File:)?\s*(.+?)(?:\.zip)?\s*$", markdown_content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Codebase Documentation"


def render_to_pdf(markdown_content: str, project_name: Optional[str] = None) -> bytes:
    """
    Converts the assembled Markdown documentation string to PDF bytes.

    Args:
        markdown_content: The full Markdown string returned by DocumentAssembler.
        project_name:     Optional project name override for the document header.
                          If omitted, the title is inferred from the first heading.

    Returns:
        PDF content as raw bytes, ready to be written to a file or returned
        as an HTTP response.

    Raises:
        ImportError:  If `markdown` or `weasyprint` are not installed.
        RuntimeError: If weasyprint fails to render the PDF.
    """
    try:
        import markdown as md
    except ImportError:
        raise ImportError(
            "The 'markdown' package is required for PDF rendering. "
            "Run: pip install markdown"
        )

    try:
        from weasyprint import HTML as WeasyprintHTML
    except ImportError:
        raise ImportError(
            "The 'weasyprint' package is required for PDF rendering. "
            "Run: pip install weasyprint"
        )

    title = project_name or _extract_project_title(markdown_content)
    logger.info(f"[Renderer] Rendering PDF for project: '{title}'")

    # ── Step 1: Markdown → HTML body ─────────────────────────────────────────
    # Extensions used:
    #   fenced_code — ```python ... ``` blocks
    #   tables      — | col | col | tables
    #   nl2br       — single newline → <br> (preserves summary line breaks)
    html_body = md.markdown(
        markdown_content,
        extensions=["fenced_code", "tables", "nl2br"],
        output_format="html",
    )

    # ── Step 2: Inject into full HTML template ────────────────────────────────
    full_html = _HTML_TEMPLATE.format(
        title=title,
        css=_CSS,
        body=html_body,
    )

    # ── Step 3: Render to PDF ─────────────────────────────────────────────────
    try:
        pdf_bytes: bytes = WeasyprintHTML(string=full_html).write_pdf()
        logger.info(f"[Renderer] PDF rendered successfully ({len(pdf_bytes):,} bytes).")
        return pdf_bytes
    except Exception as e:
        logger.error(f"[Renderer] weasyprint failed to render PDF: {e}", exc_info=True)
        raise RuntimeError(f"PDF rendering failed: {e}") from e
