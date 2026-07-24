import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver import ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


TEXTBOX_SELECTORS = [
    (By.CSS_SELECTOR, "div.ProseMirror[contenteditable='true']"),
    (By.CSS_SELECTOR, "textarea"),
    (By.CSS_SELECTOR, "[contenteditable='true']"),
]

ASSISTANT_SELECTORS = [
    (By.CSS_SELECTOR, "[data-message-author-role='assistant']"),
    (By.CSS_SELECTOR, "article"),
]

BUSY_SELECTORS = [
    (By.CSS_SELECTOR, "[data-testid='stop-button']"),
    (By.CSS_SELECTOR, "button[aria-label*='Stop']"),
]

NEW_CHAT_SELECTORS = [
    (By.CSS_SELECTOR, "a[aria-label*='New chat']"),
    (By.CSS_SELECTOR, "button[aria-label*='New chat']"),
    (By.CSS_SELECTOR, "a[href='/']"),
]

RATE_LIMIT_PHRASES = [
    "요청이 너무 많습니다",
    "요청을 너무 빠르게",
    "일시적으로 제한",
    "몇 분 후 다시 시도",
    "다시 시도해 주세요",
    "too many requests",
    "sending requests too quickly",
    "temporarily restricted",
    "try again in a few minutes",
]


@dataclass
class MacroConfig:
    chatgpt_url: str
    chrome_binary: str | None
    chrome_profile_dir: Path
    output_dir: Path
    delay_between_runs_seconds: float
    wait_timeout_seconds: int
    questions: list[dict]


@dataclass
class MacroProgress:
    total_runs: int
    completed_runs: int = 0
    current_question_id: str = ""
    current_run_number: int = 0
    current_repeat: int = 0
    last_saved_path: Path | None = None


class RateLimitDetected(RuntimeError):
    pass


def load_config(path: Path) -> MacroConfig:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)

    base_dir = path.parent
    return MacroConfig(
        chatgpt_url=raw.get("chatgpt_url", "https://chatgpt.com/"),
        chrome_binary=raw.get("chrome_binary"),
        chrome_profile_dir=(base_dir / raw.get("chrome_profile_dir", ".chrome-profile")).resolve(),
        output_dir=(base_dir / raw.get("output_dir", "answers")).resolve(),
        delay_between_runs_seconds=float(raw.get("delay_between_runs_seconds", 8)),
        wait_timeout_seconds=int(raw.get("wait_timeout_seconds", 180)),
        questions=raw.get("questions", []),
    )


def slugify(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-")
    return value[:80] or "question"


def build_driver(config: MacroConfig) -> webdriver.Chrome:
    options = ChromeOptions()
    options.add_argument(f"--user-data-dir={config.chrome_profile_dir}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("detach", False)
    if config.chrome_binary:
        options.binary_location = config.chrome_binary
    return webdriver.Chrome(options=options)


def find_first(driver: webdriver.Chrome, selectors: list[tuple[str, str]], timeout: int):
    wait = WebDriverWait(driver, timeout, ignored_exceptions=(StaleElementReferenceException,))
    last_error = None
    for by, selector in selectors:
        try:
            return wait.until(EC.element_to_be_clickable((by, selector)))
        except TimeoutException as exc:
            last_error = exc
    raise TimeoutException(f"Cannot find element for selectors: {selectors}") from last_error


def wait_until_prompt_ready(driver: webdriver.Chrome, timeout: int) -> None:
    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        assert_no_rate_limit(driver)
        try:
            find_first(driver, TEXTBOX_SELECTORS, min(3, timeout))
            return
        except TimeoutException as exc:
            last_error = exc
            time.sleep(0.5)

    raise TimeoutException("Cannot find prompt textbox.") from last_error


def get_visible_text(driver: webdriver.Chrome, selectors: list[tuple[str, str]]) -> str:
    texts: list[str] = []
    for by, selector in selectors:
        try:
            for element in driver.find_elements(by, selector):
                try:
                    if element.is_displayed() and element.text.strip():
                        texts.append(element.text)
                except StaleElementReferenceException:
                    continue
        except StaleElementReferenceException:
            continue
    return "\n".join(texts)


def rate_limit_warning_text(driver: webdriver.Chrome) -> str | None:
    dialog_text = get_visible_text(
        driver,
        [
            (By.CSS_SELECTOR, "[role='dialog']"),
            (By.CSS_SELECTOR, "[data-testid*='modal']"),
        ],
    )
    body_text = ""
    if not dialog_text:
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body_text = body.text if body else ""
        except Exception:
            body_text = ""

    combined = dialog_text or body_text
    lower = combined.lower()
    if any(phrase in lower for phrase in RATE_LIMIT_PHRASES):
        return combined.strip()
    return None


def assert_no_rate_limit(driver: webdriver.Chrome) -> None:
    warning_text = rate_limit_warning_text(driver)
    if warning_text:
        raise RateLimitDetected(warning_text)


def click_new_chat(driver: webdriver.Chrome, config: MacroConfig) -> None:
    driver.get(config.chatgpt_url)
    wait_until_prompt_ready(driver, config.wait_timeout_seconds)

    deadline = time.time() + config.wait_timeout_seconds
    while time.time() < deadline:
        assert_no_rate_limit(driver)
        for by, selector in NEW_CHAT_SELECTORS:
            for element in driver.find_elements(by, selector):
                try:
                    if element.is_displayed() and element.is_enabled():
                        element.click()
                        wait_until_prompt_ready(driver, config.wait_timeout_seconds)
                        return
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
        time.sleep(0.5)

    driver.get(config.chatgpt_url)
    wait_until_prompt_ready(driver, config.wait_timeout_seconds)


def send_question(driver: webdriver.Chrome, question: str, timeout: int) -> None:
    deadline = time.time() + timeout
    last_error = None

    while time.time() < deadline:
        assert_no_rate_limit(driver)
        try:
            textbox = find_first(driver, TEXTBOX_SELECTORS, min(10, timeout))
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", textbox)
            textbox.click()
            if textbox.tag_name.lower() == "textarea":
                textbox.clear()
                textbox.send_keys(question)
            else:
                textbox.send_keys(Keys.CONTROL, "a")
                textbox.send_keys(question)
            textbox.send_keys(Keys.ENTER)
            assert_no_rate_limit(driver)
            return
        except StaleElementReferenceException as exc:
            last_error = exc
            time.sleep(1)

    raise TimeoutException("Timed out while retrying stale ChatGPT textbox.") from last_error


def wait_for_answer(driver: webdriver.Chrome, timeout: int) -> str:
    wait = WebDriverWait(driver, timeout, ignored_exceptions=(StaleElementReferenceException,))
    wait.until(lambda d: assert_no_rate_limit(d) is None and len(get_assistant_texts(d)) > 0)

    stable_text = ""
    stable_count = 0
    deadline = time.time() + timeout
    while time.time() < deadline:
        assert_no_rate_limit(driver)
        current_texts = get_assistant_texts(driver)
        current = current_texts[-1].strip() if current_texts else ""

        if current and current == stable_text and not is_busy(driver):
            stable_count += 1
        else:
            stable_count = 0
            stable_text = current

        if stable_count >= 3:
            return stable_text

        time.sleep(2)

    raise TimeoutException("Timed out while waiting for ChatGPT answer to finish.")


def get_assistant_texts(driver: webdriver.Chrome) -> list[str]:
    for by, selector in ASSISTANT_SELECTORS:
        try:
            elements = driver.find_elements(by, selector)
            texts = [extract_text_with_links(driver, element) for element in elements if element.text.strip()]
            if texts:
                return texts
        except StaleElementReferenceException:
            return []
    return []


def extract_text_with_links(driver: webdriver.Chrome, element) -> str:
    text = driver.execute_script(
        """
        const root = arguments[0];

        function normalizeUrl(url) {
          try {
            return new URL(url, window.location.href).href;
          } catch {
            return url || "";
          }
        }

        function walk(node) {
          if (node.nodeType === Node.TEXT_NODE) {
            return node.textContent;
          }

          if (node.nodeType !== Node.ELEMENT_NODE) {
            return "";
          }

          const tag = node.tagName.toLowerCase();
          if (tag === "script" || tag === "style" || tag === "button") {
            return "";
          }

          if (tag === "br") {
            return "\\n";
          }

          let content = "";
          for (const child of node.childNodes) {
            content += walk(child);
          }

          if (tag === "a") {
            const href = normalizeUrl(node.getAttribute("href"));
            const label = content.trim() || href;
            if (href && label !== href) {
              return `${label} (${href})`;
            }
            return label;
          }

          if (["p", "div", "section", "article", "li", "ul", "ol", "pre", "table", "tr"].includes(tag)) {
            return content + "\\n";
          }

          return content;
        }

        return walk(root)
          .replace(/[ \\t]+\\n/g, "\\n")
          .replace(/\\n{3,}/g, "\\n\\n")
          .trim();
        """,
        element,
    )
    return text or element.text


def is_busy(driver: webdriver.Chrome) -> bool:
    for by, selector in BUSY_SELECTORS:
        try:
            elements = driver.find_elements(by, selector)
        except StaleElementReferenceException:
            return True

        for element in elements:
            try:
                if element.is_displayed():
                    return True
            except StaleElementReferenceException:
                return True
            except Exception:
                continue
    return False


def save_answer(output_dir: Path, question_id: str, run_number: int, question: str, answer: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    question_dir = output_dir / slugify(question_id)
    question_dir.mkdir(parents=True, exist_ok=True)
    path = question_dir / f"{timestamp}-run-{run_number:03d}.md"
    content = (
        f"# {question_id} / run {run_number}\n\n"
        f"## Question\n\n{question}\n\n"
        f"## Answer\n\n{answer}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def validate_config(config: MacroConfig) -> None:
    if not config.questions:
        raise ValueError("questions list is empty.")

    for index, item in enumerate(config.questions, start=1):
        if not item.get("text"):
            raise ValueError(f"questions[{index}] has no text.")
        repeat = int(item.get("repeat", 1))
        if repeat < 1:
            raise ValueError(f"questions[{index}] repeat must be 1 or greater.")


def total_config_runs(config: MacroConfig) -> int:
    return sum(int(item.get("repeat", 1)) for item in config.questions)


def print_rate_limit_progress(progress: MacroProgress, warning_text: str) -> None:
    stopped_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("[STOP] ChatGPT request-limit warning detected.")
    print(f"[STOPPED_AT] {stopped_at}")
    print(f"[PROGRESS] completed {progress.completed_runs}/{progress.total_runs} runs")
    if progress.current_question_id:
        print(
            "[PROGRESS] current "
            f"{progress.current_question_id} run {progress.current_run_number}/{progress.current_repeat}"
        )
    if progress.last_saved_path:
        print(f"[PROGRESS] last saved: {progress.last_saved_path}")

    first_line = warning_text.splitlines()[0] if warning_text.splitlines() else warning_text
    print(f"[WARNING] {first_line}")
    print("[STOP] Please wait a few minutes, then rerun the macro.")


def run(config_path: Path, pause_for_login: bool) -> int:
    config = load_config(config_path)
    validate_config(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.chrome_profile_dir.mkdir(parents=True, exist_ok=True)
    progress = MacroProgress(total_runs=total_config_runs(config))

    driver = build_driver(config)
    try:
        driver.get(config.chatgpt_url)

        if pause_for_login:
            input("After logging in to ChatGPT in Chrome, press Enter here...")

        wait_until_prompt_ready(driver, config.wait_timeout_seconds)

        for item in config.questions:
            question_id = item.get("id") or slugify(item["text"][:40])
            question = item["text"]
            repeat = int(item.get("repeat", 1))

            for run_number in range(1, repeat + 1):
                progress.current_question_id = question_id
                progress.current_run_number = run_number
                progress.current_repeat = repeat
                print(f"[START] {question_id} run {run_number}/{repeat}")
                try:
                    click_new_chat(driver, config)
                    send_question(driver, question, config.wait_timeout_seconds)
                    answer = wait_for_answer(driver, config.wait_timeout_seconds)
                except RateLimitDetected as exc:
                    print_rate_limit_progress(progress, str(exc))
                    return 2

                saved_path = save_answer(config.output_dir, question_id, run_number, question, answer)
                progress.completed_runs += 1
                progress.last_saved_path = saved_path
                print(f"[SAVED] {saved_path}")
                time.sleep(config.delay_between_runs_seconds)

        return 0
    finally:
        driver.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask ChatGPT questions repeatedly and save each answer.")
    default_config = Path(__file__).resolve().parents[1] / "questions.json"
    parser.add_argument("--config", default=str(default_config), help="Path to questions JSON config.")
    parser.add_argument(
        "--pause-for-login",
        action="store_true",
        help="Pause after opening Chrome so you can complete login manually.",
    )
    args = parser.parse_args()

    try:
        return run(Path(args.config).resolve(), args.pause_for_login)
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())



