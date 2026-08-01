# ChatGPT 반복 질문 매크로
(데이터셋 수집 기능은 gather-dataset폴더에 있습니다.)

Chrome에서 ChatGPT에 질문을 반복 입력하고, 각 답변을 별도의 Markdown 파일로 저장하는 Python/Selenium 매크로입니다.

## 기능

- `questions.json`에서 질문 목록과 질문별 반복 횟수를 설정할 수 있습니다.
- 각 질문 실행마다 새 채팅을 열어 이전 질문의 맥락이 섞이지 않게 합니다.
- 답변은 `answers/<질문-id>/` 폴더에 실행 회차별 `.md` 파일로 저장됩니다.
- 답변 안에 하이퍼링크가 있으면 `링크 텍스트 (URL)` 형태로 URL까지 함께 저장합니다.
- ChatGPT 화면이 리렌더링될 때 생기는 `stale element reference` 오류를 재시도하도록 보강했습니다.
- 저장된 답변에서 URL 언급률을 계산하고, GEO 평가 점수와의 상관관계를 분석할 수 있습니다.
- 전체 산점도와 질문별 산점도를 생성합니다.
- PowerShell 실행 정책에 막히지 않도록 `run.bat` 실행 파일을 제공합니다.

## 주의

- ChatGPT 로그인, 보안 확인, CAPTCHA 등은 자동으로 우회하지 않습니다. Chrome 창에서 직접 처리해야 합니다.
- 실행 중 Chrome 창을 직접 클릭하거나 새로고침하면 자동화가 실패할 수 있습니다.
- 너무 짧은 간격으로 반복 실행하면 서비스 제한에 걸릴 수 있으니 `delay_between_runs_seconds`를 넉넉히 두세요. 
- "delay_between_runs_seconds": 8 로 설정하는 것을 추천합니다.

## 설치

처음 한 번만 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m playwright install chromium
```

## 질문 설정

`questions.json` 파일을 수정하세요.

```json
{
  "chatgpt_url": "https://chatgpt.com/",
  "chrome_binary": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "chrome_profile_dir": ".chrome-profile",
  "output_dir": "answers",
  "delay_between_runs_seconds": 8,
  "wait_timeout_seconds": 600,
  "questions": [
    {
      "id": "my-question",
      "text": "여기에 질문을 입력하세요.",
      "repeat": 3
    }
  ]
}
```

설정 항목:

- `id`: 결과 저장 폴더 이름으로 사용할 질문 ID
- `text`: ChatGPT에 입력할 질문
- `repeat`: 해당 질문을 반복할 횟수
- `delay_between_runs_seconds`: 각 실행 사이 대기 시간
- `wait_timeout_seconds`: 답변 완료를 기다릴 최대 시간
- `output_dir`: 답변 저장 폴더
- `chrome_profile_dir`: 로그인 상태를 보관할 Chrome 프로필 폴더

## 실행 순서
1. run.bat : 메크로 실행
2. extract_answer_urls.py : ChatGPT 답변에서 언급횟수 추출
3. build_url_outputs.py : 언급률 계산과 url추출
4. update_preprocessed_domains.py : AI모델 입력 데이터 "domain" 지정
5. preprocess_urls.py : url크롤링 후 AI모델 입력형식으로 변환
6. evaluate.py : GEO점수 평가
7. visualize.py : ChatGPT언급률과 GEO점수간의 상관관계 계산 및 산점도 생성

## 실행

먼저 `gpt-extends` 폴더로 이동한 뒤 실행합니다.

(ex)
```powershell
cd C:\Users\frozn\Desktop\상상기업\gpt-extends
```

처음 실행하거나 CAPCHA 인증 또는 로그인이 필요할 때:

```powershell
.\run.bat --pause-for-login
```

Chrome 창이 열리면 ChatGPT에 로그인한 뒤, 터미널에서 Enter를 누르세요.

로그인 상태가 유지된 다음부터:

```powershell
.\run.bat
```

다른 설정 파일을 쓰고 싶을 때:

```powershell
.\run.bat --config questions.json
```

## 직접 실행

`run.bat` 대신 Python으로 직접 실행할 수도 있습니다.

```powershell
.\.venv\Scripts\python src\chatgpt_macro.py --config questions.json --pause-for-login
```

로그인 후 일반 실행:

```powershell
.\.venv\Scripts\python src\chatgpt_macro.py --config questions.json
```

## 결과 파일

답변은 기본적으로 아래 형식으로 저장됩니다.

```text
answers/<질문-id>/YYYYMMDD-HHMMSS-run-001.md
```

각 파일에는 질문과 답변이 함께 들어갑니다. 답변에 포함된 링크는 표시 텍스트와 실제 URL이 같이 저장됩니다.

## GEO 상관관계 테스트

이 테스트는 ChatGPT 답변에서 특정 URL이 언급되는 비율과 GEO 평가 모델의 `Total Score` 사이에 상관관계가 있는지 확인합니다.

### 1-5번: 답변 URL 언급률 산출

ChatGPT 답변을 수집한 뒤 아래 두 스크립트를 실행합니다.

```powershell
.\.venv\Scripts\python src\extract_answer_urls.py
.\.venv\Scripts\python src\build_url_outputs.py
```

생성 파일:

```text
mediate-files/answer_url_mentions.csv
mediate-files/answer_url_mentions.md
mediate-files/answer_url_mention_rates.csv
mediate-files/answer_url_mention_rates.md
mediate-files/answer_urls.txt
```

### 6-10번: GEO 평가와 시각화

6-10번 단계는 아래 명령으로 한 번에 실행합니다.

```powershell
.\.venv\Scripts\python src\run_geo_test.py
```

내부적으로 아래 순서로 실행됩니다.

1. `preprocess_urls.py`: `answer_urls.txt`의 URL을 Playwright로 크롤링하고, 본문을 Markdown으로 변환하여 GEO 모델 입력 JSONL로 저장
2. `evaluate.py`: 전처리 데이터를 GEO API에 하나씩 순차 입력하고 `Total Score` 저장
3. `visualize.py`: 언급률과 GEO 점수를 결합해 산점도와 Spearman 상관계수 생성

각 단계만 따로 실행할 수도 있습니다.

```powershell
.\.venv\Scripts\python src\preprocess_urls.py
.\.venv\Scripts\python src\evaluate.py
.\.venv\Scripts\python src\visualize.py
```

전처리를 다시 하지 않고 평가/시각화만 실행하려면:

```powershell
.\.venv\Scripts\python src\run_geo_test.py --skip-preprocess
```

중간 산출물은 모두 `mediate-files`에 저장됩니다.

```text
mediate-files/answer_url_mentions.csv
mediate-files/answer_url_mention_rates.csv
mediate-files/answer_urls.txt
mediate-files/geo_preprocessed.jsonl
mediate-files/geo_preprocess_errors.json
mediate-files/geo_scores.csv
mediate-files/geo_scores.json
mediate-files/geo_correlation_dataset.csv
mediate-files/geo_correlation_dataset.json
```

`visualize.py`의 최종 산출물만 `result-files`에 저장됩니다.

```text
result-files/geo_correlation_scatter.png
result-files/geo_correlation_summary.json
result-files/question-scatters/<question-id>.png
```

- `geo_correlation_scatter.png`: 모든 질문의 데이터를 포함한 전체 산점도
- `question-scatters/`: 질문별 개별 산점도
- `geo_correlation_summary.json`: 전체 및 질문별 Spearman 상관계수 요약

GEO 평가 API는 기본적으로 아래 주소를 사용합니다.

```text
https://desktop-75bjpd-lab4090.tail6dd0ea.ts.net:8443/evaluate
```

다른 주소를 쓰려면 `--eval-url`을 지정하거나 `GEO_EVAL_URL` 환경 변수를 설정하세요.

```powershell
.\.venv\Scripts\python src\run_geo_test.py --eval-url https://example.com/evaluate
```

평가 단계는 모델 서버에 동시에 접근하지 않도록 URL을 하나씩 순차 처리하며, 로컬 중복 실행을 막기 위해 `mediate-files/geo_evaluator.lock` 잠금 파일을 사용합니다.
이전 실행이 비정상 종료되어 잠금 파일만 남은 경우에는, `evaluate.py`가 파일 안의 PID를 확인해 종료된 프로세스의 stale lock을 자동 제거합니다.

## 문제 해결

PowerShell에서 `run.ps1` 실행이 막히는 경우:

```text
이 시스템에서 스크립트를 실행할 수 없으므로 run.ps1 파일을 로드할 수 없습니다.
```

이 경우 `run.ps1` 대신 아래 명령을 사용하세요.

```powershell
.\run.bat --pause-for-login
```

`stale element reference` 오류가 나는 경우:

- 최신 코드에는 재시도 처리가 들어가 있습니다.
- 실행 중 Chrome 창을 조작하지 말고 다시 실행해보세요.
- 계속 발생하면 `questions.json`의 `delay_between_runs_seconds` 값을 늘려보세요.

ChatGPT에 `요청이 너무 많습니다` 경고가 뜨는 경우:

- 매크로가 경고 문구를 감지하면 즉시 중단합니다.
- 터미널에 종료 시각, 완료한 실행 수, 현재 질문/회차, 마지막 저장 파일을 출력합니다.
- 몇 분 기다린 뒤 다시 실행하세요.

`Another local GEO evaluation run appears to be active` 오류가 나는 경우:

- 실제로 다른 `evaluate.py`가 실행 중이면 끝날 때까지 기다리세요.
- 이전 실행이 강제 종료된 경우 최신 `evaluate.py`는 stale lock을 자동 정리합니다.
- 계속 막히면 `mediate-files/geo_evaluator.lock` 안의 PID가 실행 중인지 확인하세요.
