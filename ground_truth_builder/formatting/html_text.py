from ..models import ExtractedDocument
from .templates import DISPLAY_TYPE, SECTION_ORDER


def _add(parts: list[str], label: str, value: str) -> None:
    value = value.strip()
    if value:
        parts.extend((f"[{label}]", value))


def format_html_text(document: ExtractedDocument) -> str:
    """Only format information recovered from rendered HTML; never inject JSON-LD values."""
    parts: list[str] = []
    _add(parts, "DOCUMENT_TYPE", DISPLAY_TYPE.get(document.document_type, "WEB_PAGE"))
    _add(parts, "TITLE", document.title)
    _add(parts, "AUTHOR", document.author)
    _add(parts, "PUBLISHED", document.published)
    _add(parts, "PUBLISHER", document.publisher)

    content = {"main_content": document.main_content, **document.sections}
    used: set[str] = set()
    for name in SECTION_ORDER.get(document.document_type, SECTION_ORDER["generic"]):
        value = content.get(name, "")
        # Avoid appending a specialised section that is already wholly present in main content.
        if name != "main_content" and value and value in document.main_content:
            continue
        _add(parts, name.upper(), value)
        used.add(name)
    for name, value in content.items():
        if name not in used and name != "main_content":
            _add(parts, name.upper(), value)
    return "\n\n".join(parts).strip()

