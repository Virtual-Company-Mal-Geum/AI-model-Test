from typing import Any

from .classification.document_type import classify_document
from .config import Settings
from .crawler import fetch_rendered_html
from .extraction.dom_content import extract_html_metadata, extract_json_ld, extract_named_sections, visible_text
from .extraction.main_content import extract_main_content
from .formatting.html_text import format_html_text
from .models import ExtractedDocument, ProcessResult
from .validation.coverage import build_coverage


async def process_record(
    context,
    record: dict[str, Any],
    settings: Settings,
    *,
    harvest_json_ld: bool = False,
) -> ProcessResult:
    url = record.get("url", "")
    try:
        raw_html = await fetch_rendered_html(context, url, settings)
        page_text = visible_text(raw_html)
        category = str(record.get("category", ""))
        json_ld = extract_json_ld(raw_html) if harvest_json_ld else record.get("json_ld")
        document_type, schema_types = classify_document(category, json_ld, page_text)
        metadata = extract_html_metadata(raw_html)
        main_content, extractor = extract_main_content(raw_html)
        sections = extract_named_sections(raw_html)
        document = ExtractedDocument(document_type=document_type, main_content=main_content, sections=sections, **metadata)
        refined = record.copy()
        if harvest_json_ld:
            refined["json_ld"] = json_ld
        refined["html_text"] = format_html_text(document)
        report = {
            "url": url,
            "status": "success" if main_content else "empty_content",
            "category": category,
            "document_type": document_type,
            "jsonld_types": schema_types,
            "content_extractor": extractor,
            "html_text_characters": len(refined["html_text"]),
            "sections_found": sorted(sections),
            "coverage": build_coverage(metadata, json_ld),
            "json_ld_items": len(json_ld) if isinstance(json_ld, list) else 0,
        }
        return ProcessResult(refined, report)
    except Exception as exc:
        return ProcessResult(
            record.copy(),
            {"url": url, "status": "failed", "error": str(exc).splitlines()[0][:500]},
        )
