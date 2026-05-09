"""One-time browser warmup: open ImmoScout24 visibly so user can clear WAF.

Cookies from this session persist to the profile dir, letting refresh.py run
headlessly afterwards. Run once after install, and re-run if scraping starts
failing again (cookies expired).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402
from playwright_stealth import Stealth  # noqa: E402

from scraper.browser_fetch import PROFILE_DIR, USER_AGENT  # noqa: E402

URL = "https://www.immobilienscout24.de/Suche/de/berlin/berlin/grundstueck-kaufen"


def main() -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Profile dir: {PROFILE_DIR}")
    print("Opening Chrome — wait for the page to load real listings, then close the window.")

    stealth = Stealth()
    with stealth.use_sync(sync_playwright()) as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=False,
            user_agent=USER_AGENT,
            locale="de-DE",
            timezone_id="Europe/Berlin",
            viewport={"width": 1366, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(URL)
        print("Browser is open. Solve the captcha if shown, browse a listing or two, then close the window.")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        context.close()
    print("Done. Profile saved.")


if __name__ == "__main__":
    main()
