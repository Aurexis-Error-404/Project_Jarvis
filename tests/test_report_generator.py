"""Smoke tests for each report template.

§11.9 requires exercising all 6 report types end-to-end (render → file
on disk). We do not validate the visual output — that is manual — but
we do assert the file renders, contains the title, and discriminating
markers for each type.
"""

import re
from pathlib import Path

import pytest

from backend.tools import report_generator


SECTIONS = [
    {"heading": "Background", "content": "This is **bold** text with `code`."},
    {"heading": "Findings", "content": "- one\n- two\n- three"},
    {"heading": "Next steps", "content": "Ship it."},
]


def _render(tmp_path: Path, report_type: str, extra: dict | None = None, **overrides) -> dict:
    kwargs = {
        "title": "Test report",
        "sections": SECTIONS,
        "research_data": '{"results": ["citation-1", "citation-2"]}',
        "output_path": str(tmp_path / f"{report_type}.html"),
        "report_type": report_type,
        "extra": extra or {},
    }
    kwargs.update(overrides)
    return report_generator.run(**kwargs)


def test_research_report(tmp_path):
    result = _render(tmp_path, "research", extra={"abstract": "A summary.", "tags": ["web"]})
    assert "error" not in result
    assert result["report_type"] == "research"
    assert Path(result["path"]).is_file()
    assert "Test report" in result["html"]
    assert "Abstract" in result["html"]


def test_diagnosis_report(tmp_path):
    result = _render(tmp_path, "diagnosis", extra={
        "severity": "high", "impact": "auth service", "root_cause": "null deref",
        "summary": "NPE in token parse.",
    })
    assert "error" not in result
    assert "diag-card" in result["html"]
    assert "References" not in result["html"]  # bibliography suppressed


def test_git_summary_report(tmp_path):
    result = _render(tmp_path, "git_summary", extra={"range_label": "last 7 days"})
    assert "error" not in result
    assert "git summary" in result["html"]


def test_audit_report(tmp_path):
    result = _render(tmp_path, "audit", extra={
        "severity_counts": {"critical": 1, "high": 2, "medium": 4, "low": 7},
        "summary": "Overall health good.",
    })
    assert "error" not in result
    assert "severity-grid" in result["html"]
    assert "Executive summary" in result["html"]


def test_executive_summary(tmp_path):
    result = _render(tmp_path, "executive", extra={"headline": "Ship Tuesday."})
    assert "error" not in result
    assert "executive briefing" in result["html"]
    # Executive skips TOC and bibliography.
    assert "nav class=\"toc\"" not in result["html"]


def test_general_report(tmp_path):
    result = _render(tmp_path, "general")
    assert "error" not in result
    assert "Test report" in result["html"]


def test_unknown_type_falls_back_to_general(tmp_path, caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="jarvis.report_generator")
    result = _render(tmp_path, "nonsense_type")
    assert "error" not in result
    assert Path(result["path"]).is_file()
    assert any("Unknown report_type" in rec.message for rec in caplog.records)


def test_markdown_is_rendered(tmp_path):
    result = _render(tmp_path, "general")
    html = result["html"]
    assert "<strong>bold</strong>" in html
    assert "<li>one</li>" in html
    assert "<code>code</code>" in html


def test_title_is_html_escaped(tmp_path):
    """Autoescape: titles with HTML entities must not be interpreted as tags."""
    result = _render(
        tmp_path, "general",
        title="<script>alert('x')</script>",
    )
    assert "<script>alert" not in result["html"]
    # Either &lt; escape or entity — just make sure the raw <script> is gone.
    assert re.search(r"&lt;script&gt;", result["html"])
