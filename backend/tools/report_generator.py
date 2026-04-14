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


def run(
    title: str,
    sections: list,
    research_data: str = "",
    output_path: str = None,
) -> dict:
    try:
        if output_path is None:
            ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
            output_path = str(REPORTS_DIR / f"jarvis_report_{ts}.html")

        generated_at = datetime.datetime.now(datetime.timezone.utc).strftime("%B %d, %Y at %H:%M UTC")

        # Pre-process section content: markdown → HTML
        processed_sections = []
        for s in sections:
            if not isinstance(s, dict):
                continue
            processed_sections.append({
                "heading": str(s.get("heading", "")),
                "content": _md_to_html(str(s.get("content", ""))),
            })

        formatted_research = _format_research_data(research_data)

        template_path = TEMPLATES_DIR / "report.html"
        if template_path.exists():
            html = _render_jinja(template_path, title, processed_sections, formatted_research, generated_at)
        else:
            html = _render_fallback(title, processed_sections, formatted_research, generated_at)
            logger.warning("report.html template not found — using fallback renderer")

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        logger.info(f"Report saved: {out.absolute()}")

        return {"path": str(out.absolute()), "html": html}

    except Exception as e:
        logger.error(f"report_generator error: {e}")
        return {"error": str(e)}


def _render_jinja(template_path, title, sections, research_data, generated_at) -> str:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(template_path.parent)), autoescape=False)
    template = env.get_template(template_path.name)
    return template.render(
        title=_html.escape(str(title)),
        sections=sections,
        research_data=_html.escape(str(research_data)) if research_data else "",
        generated_at=generated_at,
    )


def _render_fallback(title, sections, research_data, generated_at) -> str:
    """Minimal HTML report used when Docs team template isn't ready yet."""
    section_html = ""
    for s in sections:
        heading = _html.escape(str(s.get("heading", "")))
        content = s.get("content", "")  # already processed to HTML
        section_html += f"<h2>{heading}</h2><div>{content}</div>\n"

    safe_title = _html.escape(str(title))
    safe_research = _html.escape(str(research_data)) if research_data else ""
    research_html = f"<h2>Research Data</h2><pre>{safe_research}</pre>" if research_data else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{safe_title}</title>
<style>
body{{font-family:-apple-system,sans-serif;max-width:900px;margin:2em auto;padding:0 1em;
background:#0a0a0f;color:#e4e4ed;line-height:1.7}}
h1{{font-size:1.6rem;margin-bottom:8px}}
h2{{font-size:1.15rem;border-bottom:1px solid #232336;padding-bottom:6px;margin:24px 0 10px}}
pre{{background:#111119;padding:14px;border-radius:8px;overflow-x:auto;font-size:13px}}
code{{background:rgba(96,165,250,.08);padding:2px 6px;border-radius:4px;font-size:12.5px}}
pre code{{background:none;padding:0}}
table{{border-collapse:collapse;width:100%}}
th,td{{border:1px solid #232336;padding:8px 12px;font-size:13px}}
th{{background:#13131a;font-weight:600}}
ul,ol{{padding-left:20px}}
li{{margin:4px 0}}
blockquote{{border-left:3px solid #2563eb;padding:8px 14px;margin:10px 0;background:#13131a}}
a{{color:#60a5fa}}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<p><em>Generated: {generated_at}</em></p>
{section_html}
{research_html}
</body>
</html>"""
