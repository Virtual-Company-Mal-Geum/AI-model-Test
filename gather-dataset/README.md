# 데이터셋 수집 스크립트

모든 스크립트의 입출력 경로는 현재 터미널 위치가 아니라 `gather-dataset` 폴더를
기준으로 합니다. 아래 명령은 프로젝트 루트에서 실행하는 예시입니다.

## 준비

```powershell
.\.venv\Scripts\python -m pip install -r .\gather-dataset\requirements.txt
```

## 기본 파이프라인 실행 순서

```text
1. url_extracted.py
   └─ extracted_urls.txt
2. json-ld-process.py
   └─ geo_raw_dataset.jsonl
3. separate_short_records.py
   ├─ geo_raw_dataset_short.jsonl
   └─ geo_raw_dataset_passed.jsonl
4. extract_passed_urls.py
   └─ extracted_urls_passed.txt
5. compress_jsonld.py (선택)
   └─ compressed.json
```

실행 명령:

```powershell
.\.venv\Scripts\python .\gather-dataset\url_extracted.py
.\.venv\Scripts\python .\gather-dataset\json-ld-process.py
.\.venv\Scripts\python .\gather-dataset\separate_short_records.py
.\.venv\Scripts\python .\gather-dataset\extract_passed_urls.py
.\.venv\Scripts\python .\gather-dataset\compress_jsonld.py
```

`compress_jsonld.py`는 기본적으로 `geo_raw_dataset.jsonl`을 압축합니다.
통과 데이터만 압축하려면 파일 상단의 `input_file`을
`BASE_DIR / "geo_raw_dataset_passed.jsonl"`로 변경하면 됩니다.

## 대안: 도메인 목록 기반 원스톱 수집

`url_filter.py`는 위 기본 파이프라인과 별도로 사용하는 독립 실행 스크립트입니다.
`gather-dataset/domains.txt`를 다음 형식으로 작성합니다.

```text
# 카테고리,도메인
geo,example.com
news,news.example.com
```

실행:

```powershell
.\.venv\Scripts\python .\gather-dataset\url_filter.py
```

결과는 `gather-dataset/out`에 저장됩니다.

```text
out/seed_sitemaps.json
out/extracted_urls_<category>.txt
out/geo_raw_<category>.jsonl
out/urls_needs_js.txt
```

## 각 코드의 역할

- `url_extracted.py`: 지정한 블로그에서 게시글 URL 수집
- `json-ld-process.py`: URL별 본문과 JSON-LD 추출
- `separate_short_records.py`: 필드 길이를 기준으로 데이터 품질 분리
- `extract_passed_urls.py`: 통과 레코드의 URL 목록 생성
- `compress_jsonld.py`: 본문과 JSON-LD 중복을 줄여 JSON으로 압축
- `url_filter.py`: 도메인 목록을 이용한 사이트맵 기반 원스톱 수집

세부 설정값과 실행 순서는 각 Python 파일의 최상단 주석에서도 확인할 수 있습니다.
