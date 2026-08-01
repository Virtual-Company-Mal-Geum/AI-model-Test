from typing import Any


FIELD_PATHS = {
    "title": ("headline", "name"),
    "author": ("author",),
    "published": ("datePublished",),
    "publisher": ("publisher",),
}


def _contains_key(value: Any, keys: tuple[str, ...]) -> bool:
    if isinstance(value, dict):
        if any(key in value and value[key] not in (None, "", [], {}) for key in keys):
            return True
        return any(_contains_key(child, keys) for child in value.values())
    if isinstance(value, list):
        return any(_contains_key(child, keys) for child in value)
    return False


def build_coverage(html_metadata: dict[str, str], json_ld: Any) -> dict[str, dict[str, bool]]:
    return {
        name: {
            "html": bool(html_metadata.get(name)),
            "json_ld": _contains_key(json_ld, paths),
        }
        for name, paths in FIELD_PATHS.items()
    }

