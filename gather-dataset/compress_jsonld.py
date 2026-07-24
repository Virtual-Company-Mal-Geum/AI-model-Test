"""
역할: JSON/JSONL 데이터의 본문과 JSON-LD 중복을 줄여 compressed.json으로 저장한다.
설정 가이드:
  - input_file을 압축할 파일로 지정한다. 품질 통과 데이터만 처리하려면
    BASE_DIR / "geo_raw_dataset_passed.jsonl"로 변경한다.
  - output_file에서 결과 파일명을 변경할 수 있다.
  - max_html_chars는 레코드당 보존할 본문의 최대 글자 수다.
  - JSON-LD에서 제거할 필드는 recursive_compress_jsonld()의
    `if key in ["gtin", "sku"]` 목록에 추가하거나 제거한다.
  - 상품 variant 요약 규칙을 바꾸려면 compress_product_group()을 조정한다.
  - 입력은 JSON 객체, JSON 배열, JSONL을 모두 지원한다.
실행: 프로젝트 루트에서 `python gather-dataset/compress_jsonld.py`
실행 순서: 기본 파이프라인 5/5인 선택 단계
  url_extracted.py → json-ld-process.py → separate_short_records.py
  → extract_passed_urls.py → compress_jsonld.py(선택)
"""

import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
input_file = BASE_DIR / "geo_raw_dataset.jsonl"  # 필요하면 passed 파일로 변경
output_file = BASE_DIR / "compressed.json"
max_html_chars = 3000                    # html_text 최대 길이


def normalize_space(text):
    if not isinstance(text, str):
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def dedupe_lines(text):
    lines = normalize_space(text).splitlines()
    seen = set()
    result = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        key = re.sub(r"\s+", " ", line).lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(line)

    return "\n".join(result)


def split_sentences(text):
    text = normalize_space(text)
    parts = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    return [p.strip() for p in parts if p.strip()]


def dedupe_sentences(text):
    lines = dedupe_lines(text).splitlines()
    seen = set()
    result = []

    for line in lines:
        # 짧은 제목/라벨/불릿은 그대로 유지
        if len(line) < 25 or line.startswith("-") or line.startswith("•"):
            key = re.sub(r"\s+", " ", line).lower()
            if key not in seen:
                seen.add(key)
                result.append(line)
            continue

        kept = []
        for sent in split_sentences(line):
            key = re.sub(r"\s+", " ", sent).lower()
            if key in seen:
                continue

            seen.add(key)
            kept.append(sent)

        if kept:
            result.append(" ".join(kept))

    return "\n".join(result)


def compress_html_text(html_text, max_chars=3000):
    text = dedupe_sentences(html_text)

    if len(text) <= max_chars:
        return text

    sentences = split_sentences(text)
    kept = []
    total = 0

    for sent in sentences:
        if total + len(sent) + 1 > max_chars:
            break
        kept.append(sent)
        total += len(sent) + 1

    return "\n".join(kept)


def parse_json_ld(json_ld):
    if not isinstance(json_ld, str):
        return json_ld

    json_ld = json_ld.strip()

    if not json_ld:
        return ""

    try:
        return json.loads(json_ld)
    except Exception:
        return json_ld


def dedupe_array_items(items):
    seen = set()
    result = []

    for item in items:
        try:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        except Exception:
            key = str(item)

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def get_offer_value(variant, key):
    offers = variant.get("offers")
    if isinstance(offers, dict):
        return offers.get(key)
    return None


def compress_product_group(obj):
    if not isinstance(obj, dict):
        return obj

    obj = dict(obj)
    variants = obj.get("hasVariant")

    if not isinstance(variants, list):
        return obj

    product_variants = []
    related_urls = []
    sizes = []

    for v in variants:
        if not isinstance(v, dict):
            continue

        if v.get("size") is not None:
            sizes.append(str(v.get("size")))

        if v.get("@type") == "Product" or any(k in v for k in ["mpn", "gtin", "offers", "color", "size"]):
            product_variants.append(v)
        elif "url" in v:
            related_urls.append(v.get("url"))

    sizes = sorted(
        set(sizes),
        key=lambda x: float(x) if re.fullmatch(r"\d+(\.\d+)?", x) else x
    )

    representative = None

    if product_variants:
        first = product_variants[0]

        representative = {
            "@type": first.get("@type", "Product"),
            "name": first.get("name"),
            "color": first.get("color"),
            "description": first.get("description"),
            "mpn": first.get("mpn"),
            "image": first.get("image"),
        }

        offer = {}
        for key in ["@type", "url", "price", "priceCurrency", "availability", "itemCondition"]:
            value = get_offer_value(first, key)
            if value is not None:
                offer[key] = value

        if offer:
            representative["offers"] = offer

        representative = {k: v for k, v in representative.items() if v is not None}

    if sizes:
        obj["availableSizes"] = sizes

    if related_urls:
        obj["relatedVariantUrls"] = sorted(set(related_urls))

    if representative:
        obj["hasVariant"] = [representative]
    else:
        obj.pop("hasVariant", None)

    return obj


def recursive_compress_jsonld(data):
    if isinstance(data, dict):
        compressed = {}

        for key, value in data.items():
            # 사이즈별 고유 식별자는 토큰만 많이 차지해서 제거
            if key in ["gtin", "sku"]:
                continue

            compressed[key] = recursive_compress_jsonld(value)

        return compress_product_group(compressed)

    if isinstance(data, list):
        return dedupe_array_items([recursive_compress_jsonld(item) for item in data])

    if isinstance(data, str):
        return normalize_space(data)

    return data


def compress_json_ld(json_ld):
    parsed = parse_json_ld(json_ld)

    if isinstance(parsed, str):
        return normalize_space(parsed)

    compressed = recursive_compress_jsonld(parsed)

    # json_ld는 최종적으로 string이어야 하므로 문자열로 저장
    return json.dumps(compressed, ensure_ascii=False, separators=(",", ":"))


def compress_record(record):
    return {
        "url": str(record.get("url", "")),
        "html_text": compress_html_text(str(record.get("html_text", "")), max_chars=max_html_chars),
        "json_ld": compress_json_ld(record.get("json_ld", ""))
    }


def load_json_or_jsonl(path):
    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        return []

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        records = []
        for line_number, line in enumerate(raw_text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"JSONL {line_number}번째 줄이 올바른 JSON이 아닙니다: {error}"
                ) from error
        return records


def main():
    input_path = input_file
    output_path = output_file

    if not input_path.exists():
        print(f"입력 파일을 찾을 수 없습니다: {input_path}")
        return

    original_data = load_json_or_jsonl(input_path)

    if isinstance(original_data, list):
        compressed_data = [compress_record(item) for item in original_data if isinstance(item, dict)]
    elif isinstance(original_data, dict):
        compressed_data = compress_record(original_data)
    else:
        raise ValueError("입력 데이터는 JSON 객체, JSON 배열 또는 JSONL이어야 합니다.")

    output_path.write_text(
        json.dumps(compressed_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    original_len = len(json.dumps(original_data, ensure_ascii=False))
    compressed_len = len(json.dumps(compressed_data, ensure_ascii=False))
    ratio = (1 - compressed_len / original_len) * 100 if original_len else 0

    print("압축 완료")
    print(f"입력 파일: {input_file}")
    print(f"출력 파일: {output_file}")
    print(f"원본 글자 수: {original_len:,}")
    print(f"압축 글자 수: {compressed_len:,}")
    print(f"감소율: {ratio:.1f}%")

    if isinstance(compressed_data, dict):
        print(f"출력 키: {list(compressed_data.keys())}")
        print(f"url 타입: {type(compressed_data['url']).__name__}")
        print(f"html_text 타입: {type(compressed_data['html_text']).__name__}")
        print(f"json_ld 타입: {type(compressed_data['json_ld']).__name__}")


if __name__ == "__main__":
    main()
