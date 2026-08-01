from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    max_concurrent_pages: int = 5
    navigation_timeout_ms: int = 25_000
    networkidle_timeout_ms: int = 4_000
    post_load_wait_ms: int = 800
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0 Safari/537.36"
    )

