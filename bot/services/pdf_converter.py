"""Convert published HTML pages to PDF using WeasyPrint (optional dependency)."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from bot.config import PAGES_DIR

logger = logging.getLogger(__name__)

# Check once at import time whether weasyprint is available
_WEASYPRINT_AVAILABLE = importlib.util.find_spec("weasyprint") is not None
if not _WEASYPRINT_AVAILABLE:
    logger.info("weasyprint not installed — PDF generation disabled")


async def convert_html_to_pdf(page_token: str) -> str | None:
    """Convert a published HTML page to PDF.

    Returns the PDF file path or None if weasyprint is not installed or on error.
    """
    if not _WEASYPRINT_AVAILABLE:
        return None

    import asyncio

    html_path = PAGES_DIR / f"{page_token}.html"
    pdf_path = PAGES_DIR / f"{page_token}.pdf"

    if not html_path.exists():
        logger.error("HTML file not found for PDF conversion: %s", html_path)
        return None

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _render_pdf, str(html_path), str(pdf_path))
        logger.info("PDF generated: %s", pdf_path)
        return str(pdf_path)
    except Exception:
        logger.exception("Failed to convert HTML to PDF")
        return None


def _render_pdf(html_path: str, pdf_path: str) -> None:
    """Synchronous WeasyPrint rendering (runs in executor)."""
    from weasyprint import HTML

    HTML(filename=html_path).write_pdf(pdf_path)
