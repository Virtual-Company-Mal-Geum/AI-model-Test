"""
역할: 원본 JSONL을 본문/JSON-LD 길이 기준으로 통과 데이터와 짧은 데이터로 분리한다.
설정 가이드:
  - HTML_TEXT_MIN_CHARS는 허용할 본문의 최소 글자 수다.
  - JSON_LD_MIN_CHARS는 허용할 JSON-LD의 최소 글자 수다.
  - 두 조건 중 하나라도 기준 이하이면 short 파일로 분리된다.
    JSON-LD가 없는 문서도 통과시킬 경우 JSON_LD_MIN_CHARS를 0보다 작게 설정하거나
    should_separate()에서 JSON-LD 조건을 제거한다.
  - 입출력 파일을 바꿀 때는 BASE_DIR / "파일명" 형식을 유지한다.
실행: 프로젝트 루트에서 `python gather-dataset/separate_short_records.py`
실행 순서: 기본 파이프라인 3/5 (먼저 json-ld-process.py 실행)
  url_extracted.py → json-ld-process.py → separate_short_records.py
  → extract_passed_urls.py → compress_jsonld.py(선택)
"""

import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
HTML_TEXT_MIN_CHARS = 300
JSON_LD_MIN_CHARS = 100
INPUT_FILE = BASE_DIR / "geo_raw_dataset.jsonl"
SHORT_OUTPUT_FILE = BASE_DIR / "geo_raw_dataset_short.jsonl"
PASSED_OUTPUT_FILE = BASE_DIR / "geo_raw_dataset_passed.jsonl"


def field_length(record: dict, field_name: str) -> int:
    value = record.get(field_name, "")

    if value is None:
        return 0

    if isinstance(value, str):
        return len(value.strip())

    return len(json.dumps(value, ensure_ascii=False))


def should_separate(record: dict) -> bool:
    return (
        field_length(record, "html_text") <= HTML_TEXT_MIN_CHARS
        or field_length(record, "json_ld") <= JSON_LD_MIN_CHARS
    )


def write_record(file, record: dict) -> None:
    file.write(json.dumps(record, ensure_ascii=False) + "\n")


def separate_records() -> tuple[int, int, int]:
    total_count = 0
    short_count = 0
    passed_count = 0

    with (
        INPUT_FILE.open("r", encoding="utf-8") as input_file,
        SHORT_OUTPUT_FILE.open("w", encoding="utf-8") as short_file,
        PASSED_OUTPUT_FILE.open("w", encoding="utf-8") as passed_file,
    ):
        for line_number, line in enumerate(input_file, start=1):
            line = line.strip()

            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"Invalid JSON on line {line_number}: {error}") from error

            total_count += 1

            if should_separate(record):
                write_record(short_file, record)
                short_count += 1
            else:
                write_record(passed_file, record)
                passed_count += 1

    return total_count, short_count, passed_count


if __name__ == "__main__":
    total, short, passed = separate_records()
    print(f"html_text threshold: {HTML_TEXT_MIN_CHARS}")
    print(f"json_ld threshold: {JSON_LD_MIN_CHARS}")
    print(f"total: {total}")
    print(f"short: {short} -> {SHORT_OUTPUT_FILE}")
    print(f"passed: {passed} -> {PASSED_OUTPUT_FILE}")
