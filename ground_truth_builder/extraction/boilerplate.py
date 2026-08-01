import re


NOISE_PATTERNS = (
    r"^(로그인|회원가입|검색|닫기|공유|인쇄|댓글|목록)$",
    r"^(advertisement|cookie settings|sign in|subscribe)$",
    r"^(관련 기사|추천 기사|인기 기사|최근 본 상품|추천 상품)$",
)


def normalise_text(text: str) -> str:
    lines = []
    previous = ""
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line == previous:
            continue
        if any(re.fullmatch(pattern, line, flags=re.IGNORECASE) for pattern in NOISE_PATTERNS):
            continue
        lines.append(line)
        previous = line
    return "\n".join(lines).strip()

