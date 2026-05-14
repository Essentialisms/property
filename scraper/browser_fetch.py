"""Fetch ImmoScout24 pages with a real browser to bypass AWS WAF challenge.

Uses patchright + persistent Chrome profile in non-headless mode (the only
combination that defeats AWS WAF Bot Control). Window is positioned offscreen
so the cron run is non-intrusive. Local-only — not installed on Vercel.

Profile dir: ~/.cache/property-scraper-chrome
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from patchright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

logger = logging.getLogger(__name__)

PROFILE_DIR = Path(
    os.environ.get("PROPERTY_SCRAPER_PROFILE", str(Path.home() / ".cache" / "property-scraper-chrome"))
)
WAF_MAX_WAIT_S = float(os.environ.get("WAF_MAX_WAIT_S", "30"))


def _looks_like_waf(page: Page) -> bool:
    title = (page.title() or "").lower()
    return "roboter" in title or "robot" in title


def _wait_past_waf(page: Page) -> None:
    deadline = time.monotonic() + WAF_MAX_WAIT_S
    while time.monotonic() < deadline:
        if not _looks_like_waf(page):
            return
        try:
            page.wait_for_load_state("networkidle", timeout=2000)
        except PlaywrightTimeoutError:
            pass
        time.sleep(0.5)
    logger.warning("WAF challenge did not clear within %.0fs", WAF_MAX_WAIT_S)


def fetch_html(urls: list[str]) -> dict[str, str]:
    """Fetch URLs using patchright Chrome (visible but offscreen)."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    out: dict[str, str] = {}
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            no_viewport=True,
            args=[
                "--window-position=-2400,-2400",
                "--window-size=1366,900",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        for url in urls:
            logger.info("Fetching %s", url)
            html = ""
            # One retry on any transient navigation failure (ERR_NETWORK_CHANGED,
            # connection resets, etc.). A single bad page must never abort a
            # multi-hour run, so every exception here is swallowed per-URL.
            for attempt in (1, 2):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    _wait_past_waf(page)
                    try:
                        page.wait_for_load_state("networkidle", timeout=10000)
                    except PlaywrightTimeoutError:
                        pass
                    if _looks_like_waf(page):
                        logger.warning("Still on WAF page for %s", url)
                        html = ""
                    else:
                        html = page.content()
                    break
                except PlaywrightTimeoutError as e:
                    logger.warning("Timeout fetching %s (attempt %d): %s", url, attempt, e)
                except Exception as e:  # noqa: BLE001 — keep the run alive
                    logger.warning("Error fetching %s (attempt %d): %s", url, attempt, e)
                    if attempt == 1:
                        time.sleep(3)  # brief backoff before the retry
            out[url] = html
        try:
            context.close()
        except Exception:
            pass
    return out
