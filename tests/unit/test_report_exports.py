"""Report renderer and object-storage write boundary tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from botocore.exceptions import BotoCoreError

from backend.app.errors import UpstreamUnavailableError
from backend.app.schemas.analysis_report import ReportExportFormat
from backend.app.services.report_exports import render_report_export
from backend.app.services.storage import S3ObjectStorage


def test_report_renderers_preserve_reviewed_unicode_content() -> None:
    title = "课堂复盘"
    content = '- 教师确认的修改内容 <script>alert("x")</script>'

    markdown, markdown_type, markdown_extension = render_report_export(
        ReportExportFormat.MARKDOWN, title=title, content=content
    )
    html, html_type, html_extension = render_report_export(
        ReportExportFormat.HTML, title=title, content=content
    )
    pdf, pdf_type, pdf_extension = render_report_export(
        ReportExportFormat.PDF, title=title, content=content
    )

    assert markdown.decode() == f"# {title}\n\n{content}\n"
    assert markdown_type == "text/markdown; charset=utf-8"
    assert markdown_extension == "md"
    assert title in html.decode()
    assert "教师确认的修改内容" in html.decode()
    assert "<script>" not in html.decode()
    assert "&lt;script&gt;" in html.decode()
    assert html_type == "text/html; charset=utf-8"
    assert html_extension == "html"
    assert pdf.startswith(b"%PDF-")
    assert pdf_type == "application/pdf"
    assert pdf_extension == "pdf"


@pytest.mark.asyncio
async def test_storage_put_converts_sdk_failure_without_leaking_details() -> None:
    storage = S3ObjectStorage.__new__(S3ObjectStorage)
    storage._bucket = "test-bucket"
    storage._client = Mock()
    storage._client.put_object.side_effect = BotoCoreError()

    with pytest.raises(UpstreamUnavailableError) as caught:
        await storage.put("private/report.pdf", b"content", "application/pdf")

    assert "test-bucket" not in str(caught.value)
    assert "private/report.pdf" not in str(caught.value)
