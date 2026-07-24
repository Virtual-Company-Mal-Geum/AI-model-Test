from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse, urlunparse

'''
📊인용률 계산을 위한 질문 별 언급 횟수 기록📊
'''


ROOT = Path(__file__).resolve().parents[1]
ANSWERS_DIR = ROOT / "answers"
MEDIATE_DIR = ROOT / "mediate-files"
OUTPUT_CSV = MEDIATE_DIR / "answer_url_mentions.csv"
OUTPUT_MD = MEDIATE_DIR / "answer_url_mentions.md"

TUPLE_URL_RE = re.compile(r"\(([^()\n]*?),\s*(https?://[^\s)]+)")
COMMA_URL_RE = re.compile(r",\s*(https?://[^\s)]+)")
NOISE_DOMAINS = {
    "chatgpt.com",
    "www.mapbox.com",
    "mapbox.com",
    "www.openstreetmap.org",
    "openstreetmap.org",
}


def answer_body(text: str) -> str:
    marker = "## Answer"
    _, sep, body = text.partition(marker)
    return body if sep else text


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(".,;")
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    if parsed.netloc.lower() in NOISE_DOMAINS:
        return ""
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        parsed._replace(
            scheme=parsed.scheme.lower(),
            netloc=parsed.netloc.lower(),
            path=path,
            query="",
            fragment="",
        )
    )


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    body = answer_body(text)

    for match in TUPLE_URL_RE.finditer(body):
        if normalized := normalize_url(match.group(2)):
            urls.append(normalized)

    for line in body.splitlines():
        for match in COMMA_URL_RE.finditer(line):
            if normalized := normalize_url(match.group(1)):
                urls.append(normalized)

    return list(dict.fromkeys(urls))


def main() -> None:
    rows: list[dict[str, str | int]] = []
    MEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    for question_dir in sorted(path for path in ANSWERS_DIR.iterdir() if path.is_dir()):
        files = sorted(question_dir.glob("*.md"))
        counts: Counter[str] = Counter()

        for file_path in files:
            text = file_path.read_text(encoding="utf-8")
            counts.update(extract_urls(text))

        for url, mention_count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
            rows.append(
                {
                    "question": question_dir.name,
                    "url": url,
                    "mention_count": mention_count,
                    "question_repeat_count": len(files),
                }
            )

    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["question", "url", "mention_count", "question_repeat_count"],
        )
        writer.writeheader()
        writer.writerows(rows)

    with OUTPUT_MD.open("w", encoding="utf-8") as md_file:
        md_file.write("# Answer URL Mentions\n\n")
        for row in rows:
            md_file.write(
                f"({row['question']}, {row['url']}, "
                f"{row['mention_count']}, {row['question_repeat_count']})\n"
            )

    print(f"Wrote {len(rows)} rows to {OUTPUT_CSV.relative_to(ROOT)}")
    print(f"Wrote tuple list to {OUTPUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
