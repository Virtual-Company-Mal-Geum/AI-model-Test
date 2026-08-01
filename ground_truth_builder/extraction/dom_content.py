import json
import re
from bs4 import BeautifulSoup, Tag

from .boilerplate import normalise_text


SECTION_KEYWORDS = {
    "faq": ("faq", "자주 묻는", "질문과 답", "frequently asked"),
    "curriculum": ("커리큘럼", "강의 목차", "curriculum", "course outline"),
    "specifications": ("스펙", "사양", "상세 정보", "specification", "technical details"),
    "shipping": ("배송", "교환", "반품", "shipping", "returns"),
    "references": ("참고", "출처", "reference", "resources"),
}


def visible_text(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return normalise_text(soup.get_text("\n", strip=True))


def extract_html_metadata(raw_html: str) -> dict[str, str]:
    soup = BeautifulSoup(raw_html, "lxml")

    def meta(*names: str) -> str:
        for name in names:
            node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if node and node.get("content"):
                return normalise_text(str(node["content"]))
        return ""

    title_node = soup.find("title")
    return {
        "title": meta("og:title", "twitter:title") or normalise_text(title_node.get_text(" ") if title_node else ""),
        "author": meta("author", "article:author"),
        "published": meta("article:published_time", "date", "datePublished"),
        "publisher": meta("og:site_name", "application-name"),
    }


def extract_json_ld(raw_html: str) -> list[dict]:
    """Extract in-page JSON-LD after JavaScript rendering.

    Only valid JSON objects are returned. Invalid publisher markup is skipped so it
    cannot make a dataset record unusable.
    """
    soup = BeautifulSoup(raw_html, "lxml")
    items: list[dict] = []
    for node in soup.find_all("script", attrs={"type": re.compile(r"^application/ld\+json", re.I)}):
        raw = node.string or node.get_text()
        if not raw:
            continue
        raw = raw.strip().removeprefix("<!--").removesuffix("-->").strip()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            items.append(value)
        elif isinstance(value, list):
            items.extend(item for item in value if isinstance(item, dict))
    return items


def _heading_matches(text: str) -> str | None:
    lowered = text.lower()
    for section, keywords in SECTION_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return section
    return None


def _section_after_heading(heading: Tag) -> str:
    parts: list[str] = []
    level = int(heading.name[1]) if re.fullmatch(r"h[1-6]", heading.name or "") else 6
    for sibling in heading.next_siblings:
        if not isinstance(sibling, Tag):
            continue
        if re.fullmatch(r"h[1-6]", sibling.name or "") and int(sibling.name[1]) <= level:
            break
        text = sibling.get_text("\n", strip=True)
        if text:
            parts.append(text)
    return normalise_text("\n".join(parts))


def extract_named_sections(raw_html: str) -> dict[str, str]:
    soup = BeautifulSoup(raw_html, "lxml")
    sections: dict[str, str] = {}
    for heading in soup.find_all(re.compile(r"^h[1-6]$")):
        key = _heading_matches(heading.get_text(" ", strip=True))
        if key and key not in sections:
            content = _section_after_heading(heading)
            if content:
                sections[key] = content

    code_blocks = [normalise_text(code.get_text("\n")) for code in soup.find_all("pre")]
    code_blocks = [code for code in code_blocks if code]
    if code_blocks:
        sections["code"] = "\n\n".join(dict.fromkeys(code_blocks))
    return sections
