from readability import Document
import trafilatura

from .boilerplate import normalise_text


def extract_main_content(raw_html: str) -> tuple[str, str]:
    """Use independent extractors and choose the more informative clean result."""
    trafilatura_text = trafilatura.extract(
        raw_html,
        include_comments=False,
        include_tables=True,
        include_links=False,
        include_formatting=True,
        favor_precision=False,
    ) or ""
    readability_text = ""
    try:
        readable_html = Document(raw_html).summary(html_partial=True)
        readability_text = trafilatura.extract(
            readable_html,
            include_comments=False,
            include_tables=True,
            include_links=False,
            include_formatting=True,
            favor_precision=False,
        ) or ""
    except Exception:
        pass

    candidates = [(normalise_text(trafilatura_text), "trafilatura"),
                  (normalise_text(readability_text), "readability")]
    candidates = [candidate for candidate in candidates if candidate[0]]
    if not candidates:
        return "", "none"
    # Prefer substantially longer content, but do not concatenate sources: it causes duplication.
    return max(candidates, key=lambda candidate: len(candidate[0]))

