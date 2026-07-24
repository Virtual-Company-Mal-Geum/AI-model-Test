from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


# Configure question-specific domain overrides here.
# Example:
# QUESTION_DOMAIN_OVERRIDES = {
#     "GEO서비스-탐색-질문": "business",
#     "마케팅-컨설팅-탐색-질문": "business",
#     "온라인-강좌-탐색-질문": "education",
#     "이커머스-탐색-질문": "ecommerce",
# }
QUESTION_DOMAIN_OVERRIDES: dict[str, str] = {
    "GEO서비스-탐색-질문": "general",
    "마케팅-컨설팅-탐색-질문": "general",
    "온라인-강좌-탐색-질문": "education",
    "이커머스-탐색-질문": "ecommerce"
}

# Exact URL overrides win over question-based overrides.
# Use this when the same URL appears in multiple questions but must have one fixed domain.
# Example:
# URL_DOMAIN_OVERRIDES = {
#     "https://fastcampus.co.kr/": "education",
# }
URL_DOMAIN_OVERRIDES: dict[str, str] = {}

# If one URL is connected to multiple questions with different domains, choose the
# most specific domain by this priority. "general" is intentionally last.
DOMAIN_PRIORITY = [
    "ecommerce",
    "education",
    "business",
    "medical",
    "legal",
    "news",
    "academic",
    "general",
]


ROOT = Path(__file__).resolve().parents[1]
MEDIATE_DIR = ROOT / "mediate-files"
DEFAULT_PREPROCESSED = MEDIATE_DIR / "geo_preprocessed.jsonl"
DEFAULT_MENTION_RATES = MEDIATE_DIR / "answer_url_mention_rates.csv"
DOMAIN_FIELD_RE = re.compile(r'("domain"\s*:\s*")([^"]*)(")')


def load_url_questions(path: Path) -> dict[str, set[str]]:
    url_questions: dict[str, set[str]] = defaultdict(set)
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            question = (row.get("question") or "").strip()
            url = (row.get("url") or "").strip()
            if question and url:
                url_questions[url].add(question)
    return dict(url_questions)


def domain_for_url(url: str, url_questions: dict[str, set[str]]) -> str | None:
    if url in URL_DOMAIN_OVERRIDES:
        return URL_DOMAIN_OVERRIDES[url]

    questions = url_questions.get(url, set())
    matching_overrides = [
        (question, domain)
        for question, domain in QUESTION_DOMAIN_OVERRIDES.items()
        if question in questions
    ]
    if not matching_overrides:
        return None

    domains = {domain for _, domain in matching_overrides}
    if len(domains) > 1:
        chosen_domain = choose_domain(domains)
        pairs = ", ".join(f"{question}={domain}" for question, domain in matching_overrides)
        print(f"[CONFLICT] {url}: {pairs} -> {chosen_domain}")
        return chosen_domain

    return matching_overrides[0][1]


def choose_domain(domains: set[str]) -> str:
    priority = {domain: index for index, domain in enumerate(DOMAIN_PRIORITY)}
    return sorted(domains, key=lambda domain: priority.get(domain, len(priority)))[0]


def replace_domain_only(line: str, new_domain: str) -> tuple[str, str | None]:
    match = DOMAIN_FIELD_RE.search(line)
    if not match:
        return line, None

    old_domain = match.group(2)
    if old_domain == new_domain:
        return line, old_domain

    updated = line[: match.start(2)] + new_domain + line[match.end(2) :]
    return updated, old_domain


def update_preprocessed_file(preprocessed_path: Path, mention_rates_path: Path, dry_run: bool) -> int:
    url_questions = load_url_questions(mention_rates_path)
    original_lines = preprocessed_path.read_text(encoding="utf-8").splitlines(keepends=True)
    updated_lines: list[str] = []
    changed_count = 0

    for line_number, line in enumerate(original_lines, start=1):
        if not line.strip():
            updated_lines.append(line)
            continue

        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc

        url = str(record.get("url", "")).strip()
        new_domain = domain_for_url(url, url_questions)
        if not new_domain:
            updated_lines.append(line)
            continue

        updated_line, old_domain = replace_domain_only(line, new_domain)
        if old_domain is None:
            raise ValueError(f'No "domain" field found at line {line_number}: {url}')

        if updated_line != line:
            changed_count += 1
            print(f"[UPDATE] line {line_number}: {url} domain {old_domain} -> {new_domain}")

        updated_lines.append(updated_line)

    if not dry_run:
        preprocessed_path.write_text("".join(updated_lines), encoding="utf-8")

    return changed_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Update only the "domain" value in mediate-files/geo_preprocessed.jsonl.'
    )
    parser.add_argument("--preprocessed", type=Path, default=DEFAULT_PREPROCESSED)
    parser.add_argument("--mention-rates", type=Path, default=DEFAULT_MENTION_RATES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not QUESTION_DOMAIN_OVERRIDES:
        print("[NOOP] QUESTION_DOMAIN_OVERRIDES is empty. Edit the config at the top of this file first.")
        return

    changed_count = update_preprocessed_file(args.preprocessed, args.mention_rates, args.dry_run)
    mode = "would update" if args.dry_run else "updated"
    print(f"[DONE] {mode} {changed_count} lines in {args.preprocessed.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
