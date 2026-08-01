"""Create a new GEO dataset from a text file containing one URL per line."""
import argparse
import asyncio
from pathlib import Path

from .config import Settings
from .io_jsonl import write_jsonl_line


VALID_CATEGORIES = ("news", "education", "ecommerce", "tech_blog")


def read_urls(path: Path, *, keep_duplicates: bool = False) -> list[str]:
    """Read one URL per line; blank lines and # comments are ignored."""
    urls: list[str] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            url = raw.strip()
            if not url or url.startswith("#"):
                continue
            if not url.startswith(("https://", "http://")):
                raise ValueError(f"Invalid URL at {path}:{line_number}: {url}")
            if not keep_duplicates and url in seen:
                continue
            seen.add(url)
            urls.append(url)
    return urls


async def run(
    urls_path: Path,
    category: str,
    output_path: Path,
    report_path: Path,
    settings: Settings,
    *,
    keep_duplicates: bool = False,
) -> None:
    # Keep URL-file validation usable without the optional runtime crawler stack.
    from playwright.async_api import async_playwright
    from .crawler import make_context
    from .pipeline import process_record

    urls = read_urls(urls_path, keep_duplicates=keep_duplicates)
    semaphore = asyncio.Semaphore(settings.max_concurrent_pages)
    records = [
        {"url": url, "category": category, "html_text": "", "json_ld": []}
        for url in urls
    ]

    async with async_playwright() as playwright:
        browser, context = await make_context(playwright, settings)
        try:
            async def guarded(record):
                async with semaphore:
                    return await process_record(context, record, settings, harvest_json_ld=True)
            results = await asyncio.gather(*(guarded(record) for record in records))
        finally:
            await browser.close()

    with output_path.open("w", encoding="utf-8") as output, report_path.open("w", encoding="utf-8") as report:
        for result in results:
            write_jsonl_line(output, result.record)
            write_jsonl_line(report, result.report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a GEO dataset from a URL text file")
    parser.add_argument("--urls", type=Path, required=True, help="UTF-8 text file: one URL per line")
    parser.add_argument("--category", required=True, choices=VALID_CATEGORIES)
    parser.add_argument("--output", type=Path, default=Path("new_dataset.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("new_dataset_report.jsonl"))
    parser.add_argument("--concurrency", type=int, default=Settings.max_concurrent_pages)
    parser.add_argument("--keep-duplicates", action="store_true")
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    try:
        asyncio.run(
            run(
                args.urls,
                args.category,
                args.output,
                args.report,
                Settings(max_concurrent_pages=args.concurrency),
                keep_duplicates=args.keep_duplicates,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
