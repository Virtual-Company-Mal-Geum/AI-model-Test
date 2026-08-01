from __future__ import annotations

import csv
from pathlib import Path

'''
📊언급률 계산 및 모델 평가를 위한 url목록 추출📊
'''

ROOT = Path(__file__).resolve().parents[1]
MEDIATE_DIR = ROOT / "mediate-files"
INPUT_CSV = MEDIATE_DIR / "answer_url_mentions.csv"
OUTPUT_URLS_TXT = MEDIATE_DIR / "answer_urls.txt"
OUTPUT_RATES_MD = MEDIATE_DIR / "answer_url_mention_rates.md"
OUTPUT_RATES_CSV = MEDIATE_DIR / "answer_url_mention_rates.csv"


def read_rows() -> list[dict[str, str]]:
    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def mention_rate(row: dict[str, str]) -> float:
    mention_count = int(row["mention_count"])
    repeat_count = int(row["question_repeat_count"])
    if repeat_count == 0:
        return 0.0
    return mention_count / repeat_count


def write_urls_txt(rows: list[dict[str, str]]) -> None:
    urls = [row["url"]+' "domain": none' for row in rows]
    OUTPUT_URLS_TXT.write_text("\n".join(urls) + '\n', encoding="utf-8")
#^^수정함-for url,domain쌍

def write_rates(rows: list[dict[str, str]]) -> None:
    with OUTPUT_RATES_MD.open("w", encoding="utf-8") as md_file:
        md_file.write("# Answer URL Mention Rates\n\n")
        for row in rows:
            rate = mention_rate(row)
            md_file.write(f"({row['question']}, {row['url']}, {rate:.4f})\n")

    with OUTPUT_RATES_CSV.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["question", "url", "mention_rate"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "question": row["question"],
                    "url": row["url"],
                    "mention_rate": f"{mention_rate(row):.4f}",
                }
            )


def main() -> None:
    MEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    write_urls_txt(rows)
    write_rates(rows)

    print(f"Wrote {len(rows)} urls to {OUTPUT_URLS_TXT.relative_to(ROOT)}")
    print(f"Wrote mention rates to {OUTPUT_RATES_MD.relative_to(ROOT)}")
    print(f"Wrote mention rates CSV to {OUTPUT_RATES_CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
