"""Build one evaluator-input JSON file from URL/domain pairs configured below.

Run directly after installing requirements and Playwright Chromium:
    python build_test_inputs.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow this file to be run directly (for example, from the VS Code debugger).
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ground_truth_builder.config import Settings
from ground_truth_builder.crawler import make_context
from ground_truth_builder.gateway_input import prepare_gateway_input


# =============================== CONFIGURATION ===============================


MEDIATE_DIR = ROOT / "mediate-files"
INPUT_PATH = MEDIATE_DIR / "answer_urls.txt"
OUTPUT_PATH = MEDIATE_DIR / "geo_preprocessed.jsonl"
FAILURES_PATH = MEDIATE_DIR / "geo_preprocess_errors.json"

MAX_CONCURRENT_PREPARATIONS = 5
SETTINGS = Settings(max_concurrent_pages=MAX_CONCURRENT_PREPARATIONS)


@dataclass(frozen=True)
class UrlDomainPair:
    url: str
    domain: str  # news | education | ecommerce | tech_blog | None


def load_url_domain_pairs(input_path: Path) -> tuple[UrlDomainPair, ...]:
    pairs: list[UrlDomainPair] = []

    for line_number, line in enumerate(
        input_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped:
            continue

        parts = stripped.split(maxsplit=1)
        url = parts[0]
        if len(parts) == 1:
            # Keep compatibility with the previous URL-only input format.
            pairs.append(UrlDomainPair(url, "None"))
            continue

        domain_field = parts[1]
        field_name, colon, raw_domain = domain_field.strip().partition(":")
        if field_name.strip() != '"domain"' or not colon:
            raise ValueError(
                f'Invalid answer_urls.txt format at line {line_number}: '
                f'expected URL "domain": VALUE'
            )

        domain = raw_domain.strip()
        if len(domain) >= 2 and domain[0] == domain[-1] == '"':
            domain = domain[1:-1].strip()
        if not domain:
            raise ValueError(f"Empty domain at line {line_number}: {url}")
        if domain.casefold() == "none":
            domain = "None"

        pairs.append(UrlDomainPair(url, domain))

    return tuple(pairs)


URL_DOMAIN_PAIRS = load_url_domain_pairs(INPUT_PATH)

def write_json(path: Path, value: list[dict[str, Any]]) -> None:
    """Atomically replace the output so interrupted runs never leave partial JSON."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


async def convert_one(context: Any, pair: UrlDomainPair, semaphore: asyncio.Semaphore) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    async with semaphore:
        try:
            payload = await prepare_gateway_input(
                context,
                url=pair.url,
                domain=pair.domain,
                settings=SETTINGS,
            )
            # json_ld is always a Python list and becomes [] in the JSON file when absent.
            return payload, None
        except Exception as exc:
            print(f"[failed] domain={pair.domain} url={pair.url}: {exc}")
            return None, {
                "url": pair.url,
                "domain": pair.domain,
                "error": str(exc).splitlines()[0][:500],
            }


async def main_async() -> None:
    if not URL_DOMAIN_PAIRS:
        print("[warning] URL_DOMAIN_PAIRS is empty; writing empty output arrays.")

    from playwright.async_api import async_playwright

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PREPARATIONS)
    async with async_playwright() as playwright:
        browser, context = await make_context(playwright, SETTINGS)
        try:
            results = await asyncio.gather(
                *(convert_one(context, pair, semaphore) for pair in URL_DOMAIN_PAIRS)
            )
        finally:
            await browser.close()

    prepared = [payload for payload, _ in results if payload is not None]
    failures = [failure for _, failure in results if failure is not None]
    write_json(OUTPUT_PATH, prepared)
    write_json(FAILURES_PATH, failures)
    print(f"[done] prepared={len(prepared)} output={OUTPUT_PATH}")
    print(f"[done] failed={len(failures)} report={FAILURES_PATH}")


if __name__ == "__main__":
    asyncio.run(main_async())
