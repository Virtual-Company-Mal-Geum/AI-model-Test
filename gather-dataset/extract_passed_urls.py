"""
역할: 품질 검사를 통과한 JSONL 레코드의 URL만 원래 수집 순서대로 별도 저장한다.
설정 가이드:
  - EXTRACTED_URLS_FILE은 최초 URL 목록, PASSED_JSONL_FILE은 품질 통과 데이터다.
  - OUTPUT_FILE은 두 입력에 모두 존재하는 URL을 원래 순서대로 저장할 파일이다.
  - 다른 파일을 사용할 때도 BASE_DIR / "파일명" 형식을 유지한다.
  - URL 선별 기준을 바꾸는 파일이 아니라, separate_short_records.py의 결과를
    URL 목록으로 변환하는 코드이므로 품질 기준은 그 파일에서 조절한다.
실행: 프로젝트 루트에서 `python gather-dataset/extract_passed_urls.py`
실행 순서: 기본 파이프라인 4/5 (먼저 separate_short_records.py 실행)
  url_extracted.py → json-ld-process.py → separate_short_records.py
  → extract_passed_urls.py → compress_jsonld.py(선택)
"""

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
EXTRACTED_URLS_FILE = BASE_DIR / "extracted_urls.txt"
PASSED_JSONL_FILE = BASE_DIR / "geo_raw_dataset_passed.jsonl"
OUTPUT_FILE = BASE_DIR / "extracted_urls_passed.txt"


def read_url_order(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


def read_passed_urls(path: Path) -> set[str]:
    passed_urls = set()

    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error

            url = str(record.get("url", "")).strip()
            if url:
                passed_urls.add(url)

    return passed_urls


def write_urls(path: Path, urls: list[str]) -> None:
    with path.open("w", encoding="utf-8") as file:
        if urls:
            file.write("\n".join(urls) + "\n")


def extract_passed_urls() -> tuple[int, int, int]:
    original_urls = read_url_order(EXTRACTED_URLS_FILE)
    passed_urls = read_passed_urls(PASSED_JSONL_FILE)
    output_urls = [url for url in original_urls if url in passed_urls]

    write_urls(OUTPUT_FILE, output_urls)

    return len(original_urls), len(passed_urls), len(output_urls)


if __name__ == "__main__":
    original_count, passed_count, output_count = extract_passed_urls()
    print(f"extracted_urls: {original_count}")
    print(f"passed jsonl urls: {passed_count}")
    print(f"saved urls: {output_count} -> {OUTPUT_FILE}")
