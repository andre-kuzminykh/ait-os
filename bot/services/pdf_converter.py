"""Convert published HTML pages to PDF using WeasyPrint."""

from __future__ import annotations

import logging
from pathlib import Path

from bot.config import PAGES_DIR

logger = logging.getLogger(__name__)


async def convert_html_to_pdf(page_token: str) -> str | None:
    """Convert a published HTML page to PDF.

    Reads the HTML file from PAGES_DIR, renders to PDF via WeasyPrint,
    and saves alongside the HTML. Returns the PDF file path or None on error.
    """
    import asyncio

    html_path = PAGES_DIR / f"{page_token}.html"
    pdf_path = PAGES_DIR / f"{page_token}.pdf"

    if not html_path.exists():
        logger.error("HTML file not found for PDF conversion: %s", html_path)
        return None

    try:
        # Run WeasyPrint in a thread to avoid blocking the event loop
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
