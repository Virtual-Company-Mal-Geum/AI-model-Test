import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from .config import Settings
from .crawler import make_context
from .io_jsonl import read_jsonl, write_jsonl_line
from .pipeline import process_record


async def run(input_path: Path, output_path: Path, report_path: Path, settings: Settings) -> None:
    records = list(read_jsonl(input_path))
    semaphore = asyncio.Semaphore(settings.max_concurrent_pages)

    async with async_playwright() as playwright:
        browser, context = await make_context(playwright, settings)
        try:
            async def guarded(record):
                async with semaphore:
                    return await process_record(context, record, settings)
            results = await asyncio.gather(*(guarded(record) for record in records))
        finally:
            await browser.close()

    with output_path.open("w", encoding="utf-8") as output, report_path.open("w", encoding="utf-8") as report:
        for result in results:
            write_jsonl_line(output, result.record)
            write_jsonl_line(report, result.report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Conservative HTML-text builder for GEO datasets")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("refined_dataset.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("extraction_report.jsonl"))
    parser.add_argument("--concurrency", type=int, default=Settings.max_concurrent_pages)
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    asyncio.run(run(args.input, args.output, args.report, Settings(max_concurrent_pages=args.concurrency)))


if __name__ == "__main__":
    main()

