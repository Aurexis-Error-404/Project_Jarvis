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
import logging
from pathlib import Path

logger = logging.getLogger("jarvis.report_generator")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
REPORTS_DIR = Path(__file__).parent.parent / "reports"


def run(
    title: str,
    sections: list,
    research_data: str = "",
    output_path: str = None,
) -> dict:
    try:
        if output_path is None:
            ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_path = str(REPORTS_DIR / f"jarvis_report_{ts}.html")

        generated_at = datetime.datetime.utcnow().isoformat() + "Z"

        template_path = TEMPLATES_DIR / "report.html"
        if template_path.exists():
            html = _render_jinja(template_path, title, sections, research_data, generated_at)
        else:
            # Fallback: minimal HTML if template not yet provided by Docs team
            html = _render_fallback(title, sections, research_data, generated_at)
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

    env = Environment(loader=FileSystemLoader(str(template_path.parent)))
    template = env.get_template(template_path.name)
    return template.render(
        title=title,
        sections=sections,
        research_data=research_data,
        generated_at=generated_at,
    )


def _render_fallback(title, sections, research_data, generated_at) -> str:
    """Minimal HTML report used when Docs team template isn't ready yet."""
    section_html = ""
    for s in sections:
        heading = s.get("heading", "")
        content = s.get("content", "").replace("\n", "<br>")
        section_html += f"<h2>{heading}</h2><p>{content}</p>\n"

    research_html = f"<h2>Research Data</h2><pre>{research_data}</pre>" if research_data else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>{title}</title>
<style>body{{font-family:sans-serif;max-width:900px;margin:2em auto;padding:0 1em}}</style>
</head>
<body>
<h1>{title}</h1>
<p><em>Generated: {generated_at}</em></p>
{section_html}
{research_html}
</body>
</html>"""
