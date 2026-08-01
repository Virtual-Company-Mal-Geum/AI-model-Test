import re
from typing import Any


TYPE_MAP = {
    "newsarticle": "news_article",
    "article": "article",
    "blogposting": "blog_article",
    "course": "course",
    "product": "product",
}


def _walk_types(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        node_type = value.get("@type")
        if isinstance(node_type, str):
            found.add(node_type.lower())
        elif isinstance(node_type, list):
            found.update(str(item).lower() for item in node_type)
        for child in value.values():
            found.update(_walk_types(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_walk_types(child))
    return found


def classify_document(category: str, json_ld: Any, visible_text: str) -> tuple[str, list[str]]:
    """Return a content type, keeping category as a separate business label."""
    schema_types = sorted(_walk_types(json_ld))
    for schema_type in schema_types:
        if schema_type in TYPE_MAP:
            return TYPE_MAP[schema_type], schema_types

    text = visible_text.lower()
    if category == "news":
        return "news_article", schema_types
    if category == "ecommerce":
        return "product", schema_types
    if category == "tech_blog":
        return "tech_blog", schema_types
    if category == "education":
        if re.search(r"커리큘럼|수강 대상|강의 소개|course curriculum", text):
            return "course", schema_types
        return "education_article", schema_types
    return "generic", schema_types

