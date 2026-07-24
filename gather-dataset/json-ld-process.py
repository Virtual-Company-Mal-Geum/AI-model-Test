"""
역할: extracted_urls.txt의 페이지에서 본문과 JSON-LD를 추출해 geo_raw_dataset.jsonl로 저장한다.
설정 가이드:
  - INPUT_FILE과 OUTPUT_FILE은 기본 파이프라인 파일명이므로 보통 수정하지 않는다.
    다른 파일을 처리할 때만 BASE_DIR / "파일명" 형태로 변경한다.
  - 동시 요청 수는 main()의 asyncio.Semaphore(5) 숫자로 조절한다.
    서버 부담이나 오류가 크면 2~3으로 낮추고, 안정적이면 조금씩 높인다.
  - 요청 제한 시간은 fetch_html()의 ClientTimeout(total=20)으로 조절한다.
  - 본문 최대 길이는 extract_html_text()의 text[:8000] 두 곳을 같은 값으로 바꾼다.
  - User-Agent 등 요청 헤더가 필요하면 HEADERS를 수정한다.
실행: 프로젝트 루트에서 `python gather-dataset/json-ld-process.py`
실행 순서: 기본 파이프라인 2/5 (먼저 url_extracted.py 실행)
  url_extracted.py → json-ld-process.py → separate_short_records.py
  → extract_passed_urls.py → compress_jsonld.py(선택)
"""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp
import trafilatura
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
INPUT_FILE = BASE_DIR / "extracted_urls.txt"
OUTPUT_FILE = BASE_DIR / "geo_raw_dataset.jsonl"


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def clean_text(text: str) -> str:
    if not text:
        return ""

    return (
        text.strip()
        .replace("\r", "")
        .replace("\t", " ")
        .replace("\n\n\n", "\n\n")
    )


def extract_html_text(html: str) -> str:
    
    text = trafilatura.extract(html)

    if text:
        return clean_text(text[:8000])

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    return clean_text(text[:8000])


def extract_json_ld(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")

    json_ld_list = []

    scripts = soup.find_all("script", type="application/ld+json")

    for script in scripts:
        raw = script.string or script.get_text()

        if not raw:
            continue

        raw = raw.strip()

        try:
            parsed = json.loads(raw)
            json_ld_list.append(parsed)
        except json.JSONDecodeError:
            # 깨진 JSON-LD도 버리지 않고 문자열로 보관
            json_ld_list.append(raw)

    # 사용자가 원하는 형식: "json_ld": "string"
    return json.dumps(json_ld_list, ensure_ascii=False)


async def fetch_html(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        timeout = aiohttp.ClientTimeout(total=20)

        async with session.get(url, headers=HEADERS, timeout=timeout) as response:
            response.raise_for_status()
            return await response.text()

    except Exception as e:
        print(f"⚠️ Fetch 실패: {url} | {str(e)[:80]}")
        return None


async def process_url(session: aiohttp.ClientSession, url: str) -> dict | None:
    html = await fetch_html(session, url)

    if not html:
        return None

    html_text = extract_html_text(html)
    json_ld = extract_json_ld(html)

    if not html_text and json_ld == "[]":
        print(f"⚠️ 추출 결과 없음: {url}")
        return None

    return {
        "url": url,
        "html_text": html_text,
        "json_ld": json_ld
    }


async def main():
    if not INPUT_FILE.exists():
        print(f"❌ {INPUT_FILE} 파일이 없습니다.")
        print("먼저 sitemap crawler를 실행해서 extracted_urls.txt를 만들어야 합니다.")
        return

    with INPUT_FILE.open("r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    if not urls:
        print("❌ extracted_urls.txt 안에 URL이 없습니다.")
        return

    print(f"🚀 총 {len(urls)}개 URL에서 HTML 본문 + JSON-LD 추출 시작")

    semaphore = asyncio.Semaphore(5)

    async def limited_process(url):
        async with semaphore:
            print(f"🔍 처리 중: {url}")
            return await process_url(session, url)

    async with aiohttp.ClientSession() as session:
        tasks = [limited_process(url) for url in urls]
        results = await asyncio.gather(*tasks)

    valid_results = [r for r in results if r is not None]

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        for record in valid_results:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\n🎉 완료!")
    print(f"저장 위치: {OUTPUT_FILE}")
    print(f"저장 개수: {len(valid_results)}개")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
