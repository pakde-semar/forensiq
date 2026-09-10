"""Shared Jinja2Templates instance — import from here in all routers."""
import markupsafe
import re

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _highlight(text: str, q: str) -> markupsafe.Markup:
    escaped = markupsafe.escape(text)
    if not q or not q.strip():
        return escaped
    pattern = re.compile(re.escape(q.strip()), re.IGNORECASE)
    result = pattern.sub(
        lambda m: f'<mark class="search-hl">{markupsafe.escape(m.group(0))}</mark>',
        str(escaped),
    )
    return markupsafe.Markup(result)


templates.env.filters["highlight"] = _highlight
