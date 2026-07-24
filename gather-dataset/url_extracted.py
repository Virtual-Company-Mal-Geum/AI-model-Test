"""
역할: 지정한 기술 블로그를 순회해 게시글 URL을 extracted_urls.txt로 수집한다.
설정 가이드:
  - START_URLS에 수집할 사이트의 시작 URL을 추가하거나 제거한다.
  - 사이트별 게시글 주소 규칙이 명확하면 ARTICLE_PATTERNS에 정규식을 추가한다.
    규칙을 추가하지 않은 사이트는 일반 게시글 URL 판별 규칙을 사용한다.
  - MAX_DEPTH는 링크 탐색 깊이, MAX_LINKS_PER_SITE는 사이트당 최대 수집량이다.
    범위를 넓히면 실행 시간과 요청량도 함께 증가한다.
  - 제외할 경로는 EXCLUDED_PARTS, 탐색조차 하지 않을 경로는
    CRAWL_EXCLUDED_PARTS에 추가한다.
  - OUTPUT_FILE은 보통 수정하지 않는다. 모든 경로는 이 파일의 폴더 기준이다.
실행: 프로젝트 루트에서 `python gather-dataset/url_extracted.py`
실행 순서: 기본 파이프라인 1/5
  url_extracted.py → json-ld-process.py → separate_short_records.py
  → extract_passed_urls.py → compress_jsonld.py(선택)
"""

import re
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "extracted_urls.txt"
MAX_DEPTH = 2
MAX_LINKS_PER_SITE = 100
REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0"}

START_URLS = [
    "https://hyperconnect.github.io/",
    "https://techblog.woowahan.com/",
    "https://helloworld.kurly.com/",
    "https://tech.devsisters.com/",
    "https://engineering.ab180.co/",
    "https://d2.naver.com/helloworld",
    "https://meetup.nhncloud.com/",
    "https://engineering.linecorp.com/ko/blog",
    "https://tech.socar.kr/",
    "https://tech.kakao.com/",
    "https://tech.kakao.com/posts/",
    "https://toss.tech/",
    "https://oliveyoung.tech/",
    "https://dev.gmarket.com/",
    "https://tech.kakaopay.com/",
    "https://techblog.yogiyo.co.kr/",
    "https://medium.com/daangn",
    "https://medium.com/coupang-engineering",
    "https://techblog.musinsa.com/",
    "https://medium.com/wantedjobs",
    "https://techblog.gccompany.co.kr/",
    "https://techblog.lotteon.com/",
    "https://tech.socarcorp.kr/posts/",
]

ARTICLE_PATTERNS = {
    "techblog.woowahan.com": re.compile(r"^https://techblog\.woowahan\.com/\d+/?$"),
    "toss.tech": re.compile(r"^https://toss\.tech/article/.+"),
    "helloworld.kurly.com": re.compile(r"^https://helloworld\.kurly\.com/(blog|posts)/.+"),
    "tech.devsisters.com": re.compile(r"^https://tech\.devsisters\.com/(blog|posts)/.+"),
    "engineering.linecorp.com": re.compile(
        r"^https://engineering\.linecorp\.com/ko/blog/.+"
    ),
    "medium.com": re.compile(
        r"^https://medium\.com/(daangn|coupang-engineering|wantedjobs)/.+"
    ),
    "tech.kakao.com": re.compile(r"^https://tech\.kakao\.com/posts/\d+/?$"),
    "tech.socarcorp.kr": re.compile(
        r"^https://tech\.socarcorp\.kr/(dev|data|product|design)/.+\.html$"
    ),
    "d2.naver.com": re.compile(r"^https://d2\.naver\.com/helloworld/\d+/?$"),
}

EXCLUDED_PARTS = {
    "/tag/",
    "/tags/",
    "/tagged/",
    "/category/",
    "/categories/",
    "/archive",
    "/author/",
    "/authors/",
    "/page/",
    "/about",
    "/career",
    "/careers",
    "/recruit",
    "/privacy",
    "/login",
    "/signup",
}

CRAWL_EXCLUDED_PARTS = {
    "/about",
    "/career",
    "/careers",
    "/recruit",
    "/privacy",
    "/login",
    "/signup",
}

PATH_PREFIX_LIMITS = {
    "engineering.linecorp.com": "/ko/blog",
    "d2.naver.com": "/helloworld",
}

NON_HTML_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".tar",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


def get_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.lower().removeprefix("www.")


def is_same_domain(url1: str, url2: str) -> bool:
    return get_domain(url1) == get_domain(url2)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return parsed._replace(path=path, query="", fragment="").geturl()


def has_non_html_extension(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(extension) for extension in NON_HTML_EXTENSIONS)


def contains_excluded_part(url: str, excluded_parts: set[str]) -> bool:
    path = urlparse(url).path.lower()
    trimmed_path = path.rstrip("/")

    for part in excluded_parts:
        trimmed_part = part.rstrip("/")
        if part in path or trimmed_part == trimmed_path or trimmed_part in path:
            return True

    return False


def get_path_prefix_limit(start_url: str) -> str | None:
    domain = get_domain(start_url)

    if domain == "medium.com":
        first_segment = next(
            (segment for segment in urlparse(start_url).path.split("/") if segment),
            "",
        )
        return f"/{first_segment}" if first_segment else None

    return PATH_PREFIX_LIMITS.get(domain)


def is_allowed_site_path(url: str, start_url: str) -> bool:
    required_prefix = get_path_prefix_limit(start_url)
    if not required_prefix:
        return True

    path = urlparse(url).path.rstrip("/")
    required_prefix = required_prefix.rstrip("/")
    return path == required_prefix or path.startswith(required_prefix + "/")


def extract_internal_links(current_url: str, start_url: str) -> list[str]:
    response = requests.get(
        current_url,
        timeout=REQUEST_TIMEOUT,
        headers=REQUEST_HEADERS,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    links = set()

    for a in soup.find_all("a", href=True):
        absolute_url = normalize_url(urljoin(current_url, a["href"]))

        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue

        if not is_same_domain(absolute_url, start_url):
            continue

        if not is_allowed_site_path(absolute_url, start_url):
            continue

        links.add(absolute_url)

    return sorted(links)


def is_generic_article_url(url: str) -> bool:
    path = urlparse(url).path.rstrip("/")
    segments = [segment for segment in path.split("/") if segment]

    if len(segments) < 2:
        return False

    if segments[-1] in {"blog", "blogs", "post", "posts", "article", "articles"}:
        return False

    return True


def is_article_url(url: str, start_url: str) -> bool:
    if has_non_html_extension(url):
        return False

    if contains_excluded_part(url, EXCLUDED_PARTS):
        return False

    if not is_allowed_site_path(url, start_url):
        return False

    pattern = ARTICLE_PATTERNS.get(get_domain(url))
    if pattern:
        return bool(pattern.match(url))

    return is_generic_article_url(url)


def is_crawlable_url(url: str) -> bool:
    if has_non_html_extension(url):
        return False

    return not contains_excluded_part(url, CRAWL_EXCLUDED_PARTS)


def crawl_with_depth(
    start_url: str,
    max_depth: int = MAX_DEPTH,
    max_links: int = MAX_LINKS_PER_SITE,
) -> list[str]:
    start_url = normalize_url(start_url)
    visited = set()
    queued = {start_url}
    to_visit = deque([(start_url, 0)])
    collected = []
    collected_set = set()

    while to_visit and len(collected) < max_links:
        current_url, depth = to_visit.popleft()

        if current_url in visited:
            continue

        print(f"[Depth {depth}] {current_url}")
        visited.add(current_url)

        if is_article_url(current_url, start_url) and current_url not in collected_set:
            collected.append(current_url)
            collected_set.add(current_url)

            if len(collected) >= max_links:
                break

        if depth >= max_depth:
            continue

        try:
            links = extract_internal_links(current_url, start_url)
        except requests.RequestException as error:
            print(f"  skip: {error}")
            continue

        for link in links:
            if link in visited:
                continue

            link_is_article = is_article_url(link, start_url)

            if link_is_article:
                if link not in collected_set:
                    collected.append(link)
                    collected_set.add(link)

                if len(collected) >= max_links:
                    break

                continue

            if (
                is_crawlable_url(link)
                and link not in queued
                and len(queued) < max_links
            ):
                queued.add(link)
                to_visit.append((link, depth + 1))

    return collected


def collect_article_links() -> list[str]:
    all_links = []
    seen = set()

    for start_url in START_URLS:
        site_links = crawl_with_depth(start_url)
        print(f"{get_domain(start_url)}: {len(site_links)} article links")

        for link in site_links:
            if link in seen:
                continue

            seen.add(link)
            all_links.append(link)

    return all_links


def save_links(links: list[str], output_file: Path = OUTPUT_FILE) -> None:
    with open(output_file, "w", encoding="utf-8") as file:
        if links:
            file.write("\n".join(links) + "\n")


if __name__ == "__main__":
    links = collect_article_links()
    save_links(links)
    print(f"{len(links)} links saved to {OUTPUT_FILE}")
