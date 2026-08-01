import asyncio

from .config import Settings


async def fetch_rendered_html(context, url: str, settings: Settings) -> str:
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise ValueError("Record has no valid http(s) url")

    page = await context.new_page()
    try:
        response = await page.goto(
            url,
            timeout=settings.navigation_timeout_ms,
            wait_until="domcontentloaded",
        )
        if response is not None and response.status >= 400:
            raise RuntimeError(f"HTTP {response.status}")
        try:
            await page.wait_for_load_state("networkidle", timeout=settings.networkidle_timeout_ms)
        except Exception:
            # Long-polling and analytics often keep a page from becoming idle.
            pass
        await page.wait_for_timeout(settings.post_load_wait_ms)
        return await page.content()
    finally:
        await page.close()


async def make_context(playwright, settings: Settings):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(user_agent=settings.user_agent)
    return browser, context

