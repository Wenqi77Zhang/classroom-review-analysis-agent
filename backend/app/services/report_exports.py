"""Controlled server-side renderers for reviewed report exports."""

from __future__ import annotations

from html import escape
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from backend.app.schemas.analysis_report import ReportExportFormat

_EXPORT_METADATA = {
    ReportExportFormat.MARKDOWN: ("text/markdown; charset=utf-8", "md"),
    ReportExportFormat.HTML: ("text/html; charset=utf-8", "html"),
    ReportExportFormat.PDF: ("application/pdf", "pdf"),
}


def report_export_metadata(export_format: ReportExportFormat) -> tuple[str, str]:
    return _EXPORT_METADATA[export_format]


def render_report_export(
    export_format: ReportExportFormat, *, title: str, content: str
) -> tuple[bytes, str, str]:
    """Return bytes, content type, and filename extension for a gated report body."""

    content_type, extension = report_export_metadata(export_format)
    if export_format is ReportExportFormat.MARKDOWN:
        return f"# {title}\n\n{content}\n".encode(), content_type, extension
    if export_format is ReportExportFormat.HTML:
        body = escape(content)
        document = (
            "<!doctype html><html lang=\"zh-CN\"><meta charset=\"utf-8\">"
            f"<title>{escape(title)}</title>"
            "<body><main><h1>"
            f"{escape(title)}</h1><pre>{body}</pre></main></body></html>"
        )
        return document.encode(), content_type, extension
    return _render_pdf(title, content), content_type, extension


def _render_pdf(title: str, content: str) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, title=title)
    title_style = ParagraphStyle("report-title", fontName="STSong-Light", fontSize=18, leading=24)
    body_style = ParagraphStyle("report-body", fontName="STSong-Light", fontSize=11, leading=17)
    paragraphs = [Paragraph(escape(title), title_style), Spacer(1, 14)]
    for line in content.splitlines() or [""]:
        paragraphs.append(Paragraph(escape(line) or "&nbsp;", body_style))
    document.build(paragraphs)
    return stream.getvalue()
