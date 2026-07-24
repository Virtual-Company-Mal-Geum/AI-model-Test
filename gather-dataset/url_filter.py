"""
역할: domains.txt를 바탕으로 사이트맵 탐지, URL 수집, 품질 필터, JSONL 저장을 한 번에 수행한다.
설정 가이드:
  - gather-dataset/domains.txt에 `카테고리,도메인` 형식으로 수집 대상을 적는다.
    예: `tech,example.com` (https://와 마지막 /는 적지 않아도 된다.)
  - MAX_URLS_PER_DOMAIN은 도메인당 최대 URL 수, MIN_TEXT_LEN은 공백을 제외한
    최소 본문 길이, CONCURRENCY는 동시 요청 수다.
  - 제외할 URL 조각은 GARBAGE_URL_KEYWORDS에 추가한다.
  - 일반 경로에서 사이트맵을 찾아야 하면 COMMON_SITEMAP_PATHS에 경로를 추가한다.
  - 오류 페이지 문구는 ERROR_PHRASES, CSR 판별 표시는 CSR_MARKERS에 추가한다.
  - DOMAINS_FILE과 OUT_DIR은 보통 수정하지 않으며, 바꿀 때도 BASE_DIR 기준을 유지한다.
실행: 프로젝트 루트에서 `python gather-dataset/url_filter.py`
실행 순서: 기본 5단계 파이프라인과 별도로 사용하는 대안 원스톱 파이프라인(단독 실행).

domains.txt (카테고리,도메인) 하나만 준비하면 아래를 한 번에 수행:
  [1] 사이트맵 자동 탐지  (robots.txt → 관용 경로)
  [2] URL 수집            (사이트맵 재귀 파싱, 도메인당 쿼터)
  [3] 품질 필터 + 추출    (빈 깡통 제거, 본문·JSON-LD 추출)
  [4] JSONL 저장          (기존 geo_raw_dataset.jsonl 과 동일 형식 + category 필드)

실행:  python gather-dataset/url_filter.py
필요:  pip install aiohttp beautifulsoup4
중간 산출물은 out/ 폴더에 저장되므로 단계별 결과 확인 가능.
"""

import asyncio
import aiohttp
import json
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urlparse
from bs4 import BeautifulSoup

# ============ 설정 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAINS_FILE = os.path.join(BASE_DIR, "domains.txt")
OUT_DIR = os.path.join(BASE_DIR, "out")

MAX_URLS_PER_DOMAIN = 100      # 도메인당 수집 URL 수
MIN_TEXT_LEN = 300             # 본문 최소 글자 수(공백 제거)
CONCURRENCY = 15
GARBAGE_URL_KEYWORDS = ["/tag/", "/category/", "/author/", "/login", "/search", "/cart"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
COMMON_SITEMAP_PATHS = [
    "/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml",
    "/sitemap/sitemap.xml", "/news-sitemap.xml", "/sitemap-news.xml",
    "/wp-sitemap.xml", "/sitemap1.xml", "/rss", "/feed",
]
ERROR_PHRASES = [
    "페이지를 찾을 수 없", "존재하지 않는 페이지", "요청하신 페이지", "삭제되었거나",
    "접근 권한이 없", "로그인이 필요", "성인 인증", "page not found", "404 error",
]
CSR_MARKERS = ['id="root"', 'id="app"', 'id="__next"', 'id="__nuxt"', "data-reactroot"]
LOC_RE = re.compile(r"<loc>(.*?)</loc>")
ROBOTS_SITEMAP_RE = re.compile(r"^sitemap:\s*(\S+)", re.IGNORECASE | re.MULTILINE)


async def fetch_text(session, sem, url, timeout_s=15):
    async with sem:
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True) as r:
                if r.status != 200:
                    return None, r.status, ""
                ctype = r.headers.get("Content-Type", "")
                return await r.text(errors="ignore"), 200, ctype
        except Exception as e:
            return None, -1, str(e)[:40]


# ============ [1] 사이트맵 탐지 ============
async def discover_sitemaps(session, sem, domain):
    base = f"https://{domain}"
    txt, st, _ = await fetch_text(session, sem, f"{base}/robots.txt", 10)
    found = ROBOTS_SITEMAP_RE.findall(txt) if txt else []
    if not found:
        for path in COMMON_SITEMAP_PATHS:
            txt, st, _ = await fetch_text(session, sem, base + path, 10)
            if txt and any(m in txt[:500].lower() for m in ("<urlset", "<sitemapindex", "<rss", "<feed")):
                found = [base + path]
                break
    print(f"{'✅' if found else '❌'} [탐지] {domain} → {found[0] if found else '없음'}")
    return domain, [s.strip() for s in found]


# ============ [2] URL 수집 ============
class SitemapWalker:
    def __init__(self, session, sem, domain_category):
        self.session, self.sem = session, sem
        self.domain_category = domain_category      # netloc 끝부분 매칭용 {도메인: 카테고리}
        self.collected = {}                          # url -> category
        self.domain_counts = defaultdict(int)

    def category_of(self, netloc):
        for dom, cat in self.domain_category.items():
            if netloc.endswith(dom):
                return cat
        return None

    async def walk(self, sitemap_url, depth=0):
        if depth > 3:
            return
        netloc = urlparse(sitemap_url).netloc
        if self.domain_counts[netloc] >= MAX_URLS_PER_DOMAIN:
            return
        xml, st, _ = await fetch_text(self.session, self.sem, sitemap_url, 20)
        if not xml:
            return
        subs = []
        for u in LOC_RE.findall(xml):
            u = u.strip()
            if not u:
                continue
            if u.endswith(".xml") or ".xml.gz" in u:
                subs.append(u)
                continue
            nl = urlparse(u).netloc
            cat = self.category_of(nl)
            if cat is None or self.domain_counts[nl] >= MAX_URLS_PER_DOMAIN:
                continue
            if any(k in u for k in GARBAGE_URL_KEYWORDS):
                continue
            if u not in self.collected:
                self.collected[u] = cat
                self.domain_counts[nl] += 1
        if subs and self.domain_counts[netloc] < MAX_URLS_PER_DOMAIN:
            await asyncio.gather(*[self.walk(s, depth + 1) for s in subs[:30]], return_exceptions=True)


# ============ [3] 품질 필터 + 추출 ============
def extract_record(url, category, html):
    html_lower = html.lower()
    soup = BeautifulSoup(html, "html.parser")

    # JSON-LD 추출 (기존 데이터셋과 동일하게 리스트로)
    json_ld_blocks = []
    for tag in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            json_ld_blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            try:  # 흔한 오염(끝 콤마, 제어문자) 1차 정리 후 재시도
                cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
                cleaned = re.sub(r"[\x00-\x1f]", " ", cleaned)
                json_ld_blocks.append(json.loads(cleaned))
            except json.JSONDecodeError:
                pass

    # 본문 텍스트 추출
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(separator=" ")).strip()
    text_nospace = text.replace(" ", "")

    # 판정
    if len(text_nospace) < 2000:
        for p in ERROR_PHRASES:
            if p in text or p in html_lower:
                return None, f"soft404({p[:10]})"
    if len(text_nospace) < MIN_TEXT_LEN:
        if any(m in html for m in CSR_MARKERS):
            return None, "needs_js"
        return None, f"thin(len={len(text_nospace)})"

    return {"url": url, "html_text": text, "json_ld": json_ld_blocks, "category": category}, "ok"


async def collect_page(session, sem, url, category):
    html, st, info = await fetch_text(session, sem, url, 15)
    if html is None:
        return None, f"http_{st}" if st > 0 else f"fetch_error({info})"
    if "text/html" not in info:
        return None, "not_html"
    return extract_record(url, category, html)


# ============ 메인 ============
async def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    # domains.txt 로드
    domain_category = {}
    try:
        with open(DOMAINS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                cat, dom = [x.strip() for x in line.split(",", 1)]
                domain_category[dom.replace("https://", "").replace("http://", "").rstrip("/")] = cat
    except FileNotFoundError:
        print("domains.txt 가 없습니다. '카테고리,도메인' 형식으로 만들어 주세요.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    async with aiohttp.ClientSession() as session:

        # [1] 사이트맵 탐지
        print(f"\n===== [1/3] 사이트맵 탐지 ({len(domain_category)}개 도메인) =====")
        results = await asyncio.gather(*[discover_sitemaps(session, sem, d) for d in domain_category])
        seed_map = {d: sms for d, sms in results if sms}
        with open(os.path.join(OUT_DIR, "seed_sitemaps.json"), "w", encoding="utf-8") as f:
            json.dump(seed_map, f, ensure_ascii=False, indent=2)

        # [2] URL 수집
        print(f"\n===== [2/3] URL 수집 (도메인당 최대 {MAX_URLS_PER_DOMAIN}개) =====")
        walker = SitemapWalker(session, sem, domain_category)
        seeds = [sm for sms in seed_map.values() for sm in sms]
        await asyncio.gather(*[walker.walk(s) for s in seeds], return_exceptions=True)
        print(f"수집된 URL: {len(walker.collected)}개")

        # 카테고리별 URL 목록 저장
        urls_by_cat = defaultdict(list)
        for u, c in walker.collected.items():
            urls_by_cat[c].append(u)
        for cat, urls in urls_by_cat.items():
            with open(os.path.join(OUT_DIR, f"extracted_urls_{cat}.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(urls))
            print(f"  - {cat}: {len(urls)}개 → out/extracted_urls_{cat}.txt")

        # [3] 품질 필터 + 추출 + 카테고리별 저장
        print(f"\n===== [3/3] 본문·JSON-LD 추출 =====")
        items = list(walker.collected.items())
        stats = defaultdict(int)
        needs_js = []
        written = 0
        cat_files = {}   # 카테고리별 JSONL 파일 핸들
        try:
            for i in range(0, len(items), 100):  # 100개 단위 배치 (진행 표시 + 메모리)
                batch = items[i:i + 100]
                results = await asyncio.gather(*[collect_page(session, sem, u, c) for u, c in batch])
                for (u, c), (rec, reason) in zip(batch, results):
                    if rec:
                        if c not in cat_files:
                            cat_files[c] = open(os.path.join(OUT_DIR, f"geo_raw_{c}.jsonl"), "w", encoding="utf-8")
                        cat_files[c].write(json.dumps(rec, ensure_ascii=False) + "\n")
                        written += 1
                        stats["ok"] += 1
                        stats[f"ok:{c}"] += 1
                        stats["ok_with_jsonld" if rec["json_ld"] else "ok_no_jsonld"] += 1
                    elif reason == "needs_js":
                        needs_js.append(f"{c}\t{u}")
                        stats["needs_js"] += 1
                    else:
                        stats[f"reject:{reason.split('(')[0]}"] += 1
                print(f"  진행 {min(i+100, len(items))}/{len(items)} | 저장 {written}건")
        finally:
            for fh in cat_files.values():
                fh.close()

        with open(os.path.join(OUT_DIR, "urls_needs_js.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(needs_js))

    print(f"\n🎉 완료 — 카테고리별 파일이 out/ 에 저장되었습니다")
    for k in sorted(stats):
        if k.startswith("ok:"):
            print(f"  ✅ geo_raw_{k[3:]}.jsonl: {stats[k]}건")
    print(f"  (전체 {stats['ok']}건 — JSON-LD 보유 {stats['ok_with_jsonld']} / 미보유 {stats['ok_no_jsonld']})")
    print(f"  🎭 Playwright 필요: {stats['needs_js']}건 → out/urls_needs_js.txt")
    rejects = {k: v for k, v in stats.items() if k.startswith("reject:")}
    if rejects:
        print(f"  ❌ 탈락: {sum(rejects.values())}건 — " + ", ".join(f"{k[7:]} {v}" for k, v in rejects.items()))


if __name__ == "__main__":
    asyncio.run(main())
