"""Controlled server-side renderers for reviewed report exports."""

from __future__ import annotations

import re
from html import escape
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from agent.reporting.composer import _plain_text
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
        return f"# {_plain_text(title)}\n\n{content}\n".encode(), content_type, extension
    if export_format is ReportExportFormat.HTML:
        body = "".join(
            f'<h2>{escape(text)}</h2>' if kind == "section" else f'<p class="{kind}">{escape(text)}</p>'
            for kind, text in _blocks(content) if text
        )
        document = (
            "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title>"
            "<style>body{font:16px/1.8 system-ui,sans-serif;color:#233c39;margin:0}"
            "main{max-width:840px;margin:auto;padding:32px 24px}h1{font-size:28px}h2{font-size:21px;margin-top:32px}"
            "p{overflow-wrap:anywhere;margin:10px 0}.detail,.quote{font-size:14px;margin-left:16px;color:#435b57}"
            "@media print{main{padding:0}h2{break-after:avoid}p{orphans:3;widows:3}}</style></head>"
            "<body><main><h1>"
            f"{escape(title)}</h1>{body}</main></body></html>"
        )
        return document.encode(), content_type, extension
    return _render_pdf(title, content), content_type, extension


def _blocks(content: str):
    for line in content.splitlines():
        kind = "section" if line.startswith("## ") else "quote" if line.startswith("    - ") else "detail" if line.startswith("  - ") else "conclusion"
        text = line[3:] if kind == "section" else re.sub(r"^\s*-\s+", "", line)
        yield kind, re.sub(r"\\([\\`*_{}\[\]<>#+!|])", r"\1", text)


def _render_pdf(title: str, content: str) -> bytes:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    stream = BytesIO()
    document = SimpleDocTemplate(stream, pagesize=A4, title=title)
    title_style = ParagraphStyle("report-title", fontName="STSong-Light", fontSize=18, leading=26, wordWrap="CJK")
    body_style = ParagraphStyle("report-body", fontName="STSong-Light", fontSize=11, leading=18, wordWrap="CJK", spaceAfter=6)
    styles = {
        "section": ParagraphStyle("report-section", parent=body_style, fontSize=14, leading=22, spaceBefore=14, keepWithNext=True),
        "conclusion": body_style,
        "detail": ParagraphStyle("report-detail", parent=body_style, fontSize=9, leading=15, leftIndent=12),
        "quote": ParagraphStyle("report-quote", parent=body_style, fontSize=10, leading=16, leftIndent=18),
    }
    paragraphs = [Paragraph(escape(title), title_style), Spacer(1, 14)]
    for kind, text in _blocks(content):
        if text:
            paragraphs.append(Paragraph(escape(text), styles[kind]))

    def page_number(canvas, _document):
        canvas.saveState()
        canvas.setFont("STSong-Light", 9)
        canvas.drawCentredString(A4[0] / 2, 30, f"第 {canvas.getPageNumber()} 页")
        canvas.restoreState()

    document.build(paragraphs, onFirstPage=page_number, onLaterPages=page_number)
    return stream.getvalue()
