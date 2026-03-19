"""HTML page assembly and publication."""

import logging
from pathlib import Path

import aiofiles
from jinja2 import Environment, FileSystemLoader

from bot.config import PAGES_BASE_URL, PAGES_DIR, TEMPLATES_DIR

logger = logging.getLogger(__name__)

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=False,  # HTML is pre-generated
)


async def publish_page(
    page_token: str,
    narrative: dict,
    mermaid_code: str,
) -> str | None:
    """Render HTML template with narrative + Mermaid and save to disk.

    Returns the public URL or None on failure.
    """
    try:
        template = _env.get_template("asis_page.html")
        html = template.render(
            title=narrative.get("title", "AS-IS Process"),
            goal=narrative.get("goal", ""),
            summary=narrative.get("summary", ""),
            triggers_html=narrative.get("triggers_html", ""),
            inputs_html=narrative.get("inputs_html", ""),
            outputs_html=narrative.get("outputs_html", ""),
            roles_html=narrative.get("roles_html", ""),
            systems_html=narrative.get("systems_html", ""),
            artifacts_html=narrative.get("artifacts_html", ""),
            stages_html=narrative.get("stages_html", ""),
            metrics_html=narrative.get("metrics_html", ""),
            pain_points_html=narrative.get("pain_points_html", ""),
            automation_candidates_html=narrative.get(
                "automation_candidates_html", ""
            ),
            mermaid_code=mermaid_code,
        )

        PAGES_DIR.mkdir(parents=True, exist_ok=True)
        file_path = PAGES_DIR / f"{page_token}.html"

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(html)

        url = f"{PAGES_BASE_URL.rstrip('/')}/{page_token}.html"
        logger.info("Published page: %s", url)
        return url

    except Exception:
        logger.exception("Failed to publish page")
        return None
