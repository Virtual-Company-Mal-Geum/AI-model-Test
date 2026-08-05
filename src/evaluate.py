from __future__ import annotations

import argparse
import csv
import ctypes
import json
import os
import re
import ssl
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
MEDIATE_DIR = ROOT / "mediate-files"
DEFAULT_INPUT = MEDIATE_DIR / "geo_preprocessed.jsonl"
DEFAULT_MENTION_RATES = MEDIATE_DIR / "answer_url_mention_rates.csv"
DEFAULT_SCORES_CSV = MEDIATE_DIR / "geo_scores.csv"
DEFAULT_SCORES_JSON = MEDIATE_DIR / "geo_scores.json"
DEFAULT_JOINED_CSV = MEDIATE_DIR / "geo_correlation_dataset.csv"
DEFAULT_JOINED_JSON = MEDIATE_DIR / "geo_correlation_dataset.json"
DEFAULT_API_URL = os.getenv(
    "GEO_EVAL_URL",
    "https://desktop-75bjpd-lab4090.tail6dd0ea.ts.net:8443/evaluate",
)
LOCK_FILE = MEDIATE_DIR / "geo_evaluator.lock"
STILL_ACTIVE = 259


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False

    if os.name == "nt":
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def stale_lock_pid(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        pid = int(raw)
    except (FileNotFoundError, ValueError):
        return None
    return None if is_process_alive(pid) else pid


class SingleEvaluatorLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "SingleEvaluatorLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stale_pid = stale_lock_pid(self.path)
        if stale_pid is not None:
            print(f"[lock] Removing stale GEO evaluator lock from finished PID {stale_pid}")
            self.path.unlink(missing_ok=True)

        try:
            self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(self.fd, str(os.getpid()).encode("utf-8"))
        except FileExistsError as exc:
            raise RuntimeError(
                f"Another local GEO evaluation run appears to be active: {self.path}"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.fd is not None:
            os.close(self.fd)
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load evaluator records from either a JSON array or JSON Lines file."""
    raw_text = path.read_text(encoding="utf-8-sig").strip()
    if not raw_text:
        return []

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        records: list[Any] = []
        for line_number, line in enumerate(raw_text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSONL in {path} at line {line_number}: {exc.msg} "
                    f"(column {exc.colno})"
                ) from exc
    else:
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            records = [parsed]
        else:
            raise ValueError(
                f"Expected a JSON object, JSON array, or JSONL records in {path}; "
                f"got {type(parsed).__name__}"
            )

    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(
                f"Expected record {index} in {path} to be a JSON object; "
                f"got {type(record).__name__}"
            )
    return records


def load_mention_rates(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def post_json(url: str, payload: dict[str, Any], timeout: int, verify_ssl: bool) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    context = None if verify_ssl else ssl._create_unverified_context()
    with urlopen(request, timeout=timeout, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def extract_total_score(response: dict[str, Any]) -> float | None:
    """Extract total_score from structured or text-based model responses."""

    def parse_score(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            match = re.fullmatch(
                r"\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*100)?\s*",
                value,
            )
            if match:
                return float(match.group(1))
        return None

    def find_structured(value: Any) -> float | None:
        if isinstance(value, dict):
            for key, nested_value in value.items():
                normalized_key = re.sub(r"[\s_-]+", "", str(key)).casefold()
                if normalized_key == "totalscore":
                    score = parse_score(nested_value)
                    if score is not None:
                        return score
            for nested_value in value.values():
                score = find_structured(nested_value)
                if score is not None:
                    return score
        elif isinstance(value, list):
            for nested_value in value:
                score = find_structured(nested_value)
                if score is not None:
                    return score
        return None

    structured_score = find_structured(response)
    if structured_score is not None:
        return structured_score

    content = response.get("content") or response.get("result") or response.get("output") or response
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    match = re.search(
        r'["\'`]?total(?:\s+|_+|-+)score["\'`]?\s*[:=]\s*'
        r'["\']?([0-9]+(?:\.[0-9]+)?)(?:\s*/\s*100)?["\']?',
        content,
        re.I,
    )
    return float(match.group(1)) if match else None


def write_scores(csv_path: Path, json_path: Path, rows: list[dict[str, Any]]) -> None:
    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["url", "Total Score", "status", "error"])
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "url": row["url"],
                    "Total Score": row.get("Total Score", ""),
                    "status": row.get("status", ""),
                    "error": row.get("error", ""),
                }
            )
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def write_joined(csv_path: Path, json_path: Path, rows: list[dict[str, Any]]) -> None:
    with csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["question", "url", "Mention Rate", "Total Score"])
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate preprocessed URLs with the GEO model API.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--mention-rates", type=Path, default=DEFAULT_MENTION_RATES)
    parser.add_argument("--scores-csv", type=Path, default=DEFAULT_SCORES_CSV)
    parser.add_argument("--scores-json", type=Path, default=DEFAULT_SCORES_JSON)
    parser.add_argument("--joined-csv", type=Path, default=DEFAULT_JOINED_CSV)
    parser.add_argument("--joined-json", type=Path, default=DEFAULT_JOINED_JSON)
    parser.add_argument("--eval-url", default=DEFAULT_API_URL)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--sleep", type=float, default=1.0)
    parser.add_argument("--verify-ssl", action="store_true")
    args = parser.parse_args()

    MEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    records = load_jsonl(args.input)
    mentions = load_mention_rates(args.mention_rates)
    records_by_url = {record["url"]: record for record in records}

    score_rows: list[dict[str, Any]] = []
    score_by_url: dict[str, float] = {}

    with SingleEvaluatorLock(LOCK_FILE):
        for index, record in enumerate(records, start=1):
            url = record["url"]
            print(f"[{index}/{len(records)}] evaluate {url}")
            try:
                response = post_json(args.eval_url, record, args.timeout, args.verify_ssl)
                total_score = extract_total_score(response)
                if total_score is None:
                    raise ValueError("Total Score not found in model response")
                score_by_url[url] = total_score
                score_rows.append(
                    {
                        "url": url,
                        "Total Score": total_score,
                        "status": "success",
                        "raw_response": response,
                    }
                )
            except Exception as exc:
                score_rows.append({"url": url, "status": "error", "error": str(exc)})
                print(f"[error] {url}: {str(exc).splitlines()[0]}")

            write_scores(args.scores_csv, args.scores_json, score_rows)
            time.sleep(args.sleep)

    joined_rows: list[dict[str, Any]] = []
    for mention in mentions:
        url = mention["url"]
        if url not in records_by_url or url not in score_by_url:
            continue
        joined_rows.append(
            {
                "question": mention["question"],
                "url": url,
                "Mention Rate": float(mention["mention_rate"]),
                "Total Score": score_by_url[url],
            }
        )

    write_joined(args.joined_csv, args.joined_json, joined_rows)
    print(f"Wrote scores to {args.scores_csv.relative_to(ROOT)}")
    print(f"Wrote joined dataset to {args.joined_csv.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
