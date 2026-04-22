"""
generate_html_report tool — renders a Jinja2 HTML report and saves to disk.

Parameters (from prompts/tool_schema.md):
  title: str              — report title (must be project-specific)
  sections: list[dict]    — list of {heading, content} dicts
  research_data: str      — raw research results from web_research (citations)
  output_path: str        — file path to save (default: reports/jarvis_report_{ts}.html)

Template is owned by Docs team (backend/templates/report.html).
Do NOT edit the template — only call it.
Coordinate on template variables: title, sections, research_data, generated_at.
"""

import datetime
import html as _html
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger("jarvis.report_generator")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


def _md_to_html(text: str) -> str:
    """Convert markdown content to HTML for report sections.

    Handles: bold, italic, inline code, code blocks, headers,
    bullet lists, numbered lists, links, blockquotes, hr, paragraphs.
    """
    if not text:
        return ""

    lines = text.split("\n")
    html_parts = []
    in_code_block = False
    in_list = None  # "ul" or "ol"
    paragraph_buffer = []

    def flush_paragraph():
        if paragraph_buffer:
            p_text = " ".join(paragraph_buffer)
            html_parts.append(f"<p>{_inline_md(p_text)}</p>")
            paragraph_buffer.clear()

    def close_list():
        nonlocal in_list
        if in_list:
            html_parts.append(f"</{in_list}>")
            in_list = None

    for line in lines:
        stripped = line.strip()

        # Code blocks (``` fenced)
        if stripped.startswith("```"):
            if in_code_block:
                html_parts.append("</code></pre>")
                in_code_block = False
            else:
                flush_paragraph()
                close_list()
                lang = stripped[3:].strip()
                html_parts.append(f'<pre><code class="language-{_html.escape(lang)}">' if lang else "<pre><code>")
                in_code_block = True
            continue

        if in_code_block:
            html_parts.append(_html.escape(line))
            html_parts.append("\n")
            continue

        # Blank line — end paragraph and list
        if not stripped:
            flush_paragraph()
            close_list()
            continue

        # Horizontal rule
        if re.match(r'^-{3,}$|^\*{3,}$|^_{3,}$', stripped):
            flush_paragraph()
            close_list()
            html_parts.append("<hr>")
            continue

        # Headers (h3-h4 only — h2 is section heading)
        hdr = re.match(r'^(#{3,4})\s+(.+)', stripped)
        if hdr:
            flush_paragraph()
            close_list()
            level = len(hdr.group(1))
            html_parts.append(f"<h{level}>{_inline_md(hdr.group(2))}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            flush_paragraph()
            close_list()
            html_parts.append(f"<blockquote>{_inline_md(stripped[2:])}</blockquote>")
            continue

        # Unordered list item
        ul_match = re.match(r'^[-*+]\s+(.+)', stripped)
        if ul_match:
            flush_paragraph()
            if in_list != "ul":
                close_list()
                html_parts.append("<ul>")
                in_list = "ul"
            html_parts.append(f"<li>{_inline_md(ul_match.group(1))}</li>")
            continue

        # Ordered list item
        ol_match = re.match(r'^\d+[.)]\s+(.+)', stripped)
        if ol_match:
            flush_paragraph()
            if in_list != "ol":
                close_list()
                html_parts.append("<ol>")
                in_list = "ol"
            html_parts.append(f"<li>{_inline_md(ol_match.group(1))}</li>")
            continue

        # Regular text — accumulate for paragraph
        close_list()
        paragraph_buffer.append(stripped)

    # Flush remaining
    if in_code_block:
        html_parts.append("</code></pre>")
    flush_paragraph()
    close_list()

    return "\n".join(html_parts)


def _inline_md(text: str) -> str:
    """Process inline markdown: bold, italic, code, links."""
    # Inline code (before escaping)
    parts = re.split(r'(`[^`]+`)', text)
    processed = []
    for part in parts:
        if part.startswith('`') and part.endswith('`'):
            processed.append(f"<code>{_html.escape(part[1:-1])}</code>")
        else:
            s = _html.escape(part)
            # Bold + italic
            s = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', s)
            # Bold
            s = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', s)
            # Italic
            s = re.sub(r'\*(.+?)\*', r'<em>\1</em>', s)
            # Links
            s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
            processed.append(s)
    return "".join(processed)


def _format_research_data(raw: str) -> str:
    """Format research data for readable display."""
    if not raw:
        return ""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        return json.dumps(data, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return str(raw)


# Report-type → template filename. `general` is the safe fallback when the
# caller passes an unknown type — we log a warning and render anyway so a
# typo'd tool call never fails the query outright.
TEMPLATES = {
    "research":    "research_report.html",
    "diagnosis":   "diagnosis_report.html",
    "git_summary": "git_summary_report.html",
    "audit":       "audit_report.html",
    "executive":   "executive_summary.html",
    "general":     "general_report.html",
}


def run(
    title: str,
    sections: list,
    research_data: str = "",
    output_path: str = None,
    report_type: str = "research",
    extra: dict = None,
) -> dict:
    try:
        if output_path is None:
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = str(REPORTS_DIR / f"jarvis_report_{ts}.html")

        generated_at = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%B %d, %Y at %H:%M UTC"
        )

        # Pre-process section content: markdown → HTML
        processed_sections = []
        for s in sections or []:
            if not isinstance(s, dict):
                continue
            processed_sections.append({
                "heading": str(s.get("heading", "")),
                "content": _md_to_html(str(s.get("content", ""))),
            })

        formatted_research = _format_research_data(research_data)

        template_name = TEMPLATES.get(report_type)
        if template_name is None:
            logger.warning(
                f"Unknown report_type '{report_type}' — falling back to 'general'"
            )
            template_name = TEMPLATES["general"]

        html = _render_jinja(
            template_name=template_name,
            title=title,
            sections=processed_sections,
            research_data=formatted_research,
            generated_at=generated_at,
            extra=extra or {},
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        logger.info(f"Report saved ({report_type}): {out.absolute()}")

        return {"path": str(out.absolute()), "html": html, "report_type": report_type}

    except Exception as e:
        logger.error(f"report_generator error: {e}")
        return {"error": str(e)}


def _render_jinja(
    *,
    template_name: str,
    title: str,
    sections: list,
    research_data: str,
    generated_at: str,
    extra: dict,
) -> str:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        # Autoescape by default; section `content` is already HTML-processed
        # and marked with `|safe` in the template.
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template(template_name)
    return template.render(
        title=str(title),
        sections=sections,
        research_data=str(research_data) if research_data else "",
        generated_at=generated_at,
        **extra,
    )
