from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from markdownify import markdownify as md
from playwright.async_api import BrowserContext, async_playwright


ROOT = Path(__file__).resolve().parents[1]
MEDIATE_DIR = ROOT / "mediate-files"
DEFAULT_INPUT = MEDIATE_DIR / "answer_urls.txt"
DEFAULT_OUTPUT = MEDIATE_DIR / "geo_preprocessed.jsonl"
DEFAULT_ERRORS = MEDIATE_DIR / "geo_preprocess_errors.json"
MAX_CONCURRENT_PAGES = 5


def normalize_url(raw_url: str) -> str:
    raw_url = raw_url.strip().strip(".,);]}>\"'")
    if not raw_url:
        return ""

    parsed = urlparse(raw_url if re.match(r"^https?://", raw_url, re.I) else f"https://{raw_url}")
    if not parsed.netloc:
        return ""

    normalized = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
    )
    return urlunparse(normalized)


def read_urls(path: Path) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = normalize_url(line)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def compact_markdown(markdown_text: str, limit: int = 8000) -> str:
    markdown_text = " ".join(markdown_text.split())
    if len(markdown_text) <= limit:
        return markdown_text
    return markdown_text[:limit].rsplit(" ", 1)[0]


def categorize_domain(url: str, json_ld: list[Any], meta_tags: dict[str, str]) -> str:
    text_hints = f"{url} {str(json_ld)} {str(meta_tags)}".lower()

    if "product" in text_hints or "offer" in text_hints or "price" in text_hints or "/shop/" in url:
        return "ecommerce"
    if "newsarticle" in text_hints or "article" in text_hints or "/news/" in url:
        return "news"
    if "ac.kr" in url or ".edu" in url or "scholarlyarticle" in text_hints:
        return "academic"

    return "general"


async def extract_record(
    context: BrowserContext,
    url: str,
    semaphore: asyncio.Semaphore,
    text_limit: int,
) -> tuple[dict[str, Any] | None, dict[str, str] | None]:
    async with semaphore:
        page = await context.new_page()
        try:
            print(f"[crawl] {url}")
            await page.goto(url, timeout=15000, wait_until="domcontentloaded")

            extracted_json: list[Any] = []
            for tag in await page.locator('script[type="application/ld+json"]').all():
                content = (await tag.inner_text()).strip()
                if not content:
                    continue
                try:
                    extracted_json.append(json.loads(content))
                except json.JSONDecodeError:
                    continue

            meta_tags: dict[str, str] = {}
            selectors = 'meta[property^="og:"], meta[name^="twitter:"], meta[name="description"]'
            for loc in await page.locator(selectors).all():
                key = await loc.get_attribute("property") or await loc.get_attribute("name")
                val = await loc.get_attribute("content")
                if key and val:
                    meta_tags[key] = val

            html_content = ""
            if await page.locator("article").count() > 0:
                html_content = await page.locator("article").first.inner_html()
            elif await page.locator("main").count() > 0:
                html_content = await page.locator("main").first.inner_html()
            else:
                html_content = await page.locator("body").inner_html()

            markdown_text = compact_markdown(
                md(html_content, heading_style="ATX", strip=["script", "style", "iframe"]).strip(),
                text_limit,
            )
            domain_category = categorize_domain(url, extracted_json, meta_tags)

            if extracted_json or markdown_text or meta_tags:
                return (
                    {
                        "url": url,
                        "domain": domain_category,
                        "meta_tags": meta_tags,
                        "json_ld": extracted_json,
                        "html_text": markdown_text,
                    },
                    None,
                )

            return None, {"url": url, "error": "No JSON-LD, meta tags, or markdown text extracted"}
        except Exception as exc:
            error_msg = str(exc).splitlines()[0] if str(exc).splitlines() else "Unknown Error"
            print(f"[skip] {url}: {error_msg}")
            return None, {"url": url, "error": error_msg}
        finally:
            await page.close()


async def run(input_path: Path, output_path: Path, errors_path: Path, concurrency: int, text_limit: int) -> None:
    MEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    urls = read_urls(input_path)
    output_path.write_text("", encoding="utf-8")

    print(f"Starting semantic extraction for {len(urls)} URLs...")
    semaphore = asyncio.Semaphore(concurrency)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0"
        )
        tasks = [extract_record(context, url, semaphore, text_limit) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        await browser.close()

    with output_path.open("a", encoding="utf-8") as output_file:
        for record, error in results:
            if record:
                records.append(record)
                output_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            if error:
                errors.append(error)

    errors_path.write_text(json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} records to {output_path.relative_to(ROOT)}")
    print(f"Wrote {len(errors)} errors to {errors_path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl URLs and convert them to GEO evaluator input JSONL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--concurrency", type=int, default=MAX_CONCURRENT_PAGES)
    parser.add_argument("--text-limit", type=int, default=8000)
    args = parser.parse_args()

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    asyncio.run(run(args.input, args.output, args.errors, args.concurrency, args.text_limit))


if __name__ == "__main__":
    main()
