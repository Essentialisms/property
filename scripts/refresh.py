"""Scrape ImmoScout24 with a headless browser and upload the dataset to Vercel Blob.

Run locally (datacenter IPs are blocked, AWS WAF requires a real browser).
Designed to be run by launchd daily.

Reads no env vars; relies on the local `vercel` CLI being authenticated.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser_fetch import fetch_html  # noqa: E402
from scraper.parser import parse_search_results, parse_total_pages  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("refresh")

BASE = "https://www.immobilienscout24.de/Suche/de/berlin/berlin"
PROPERTY_TYPES = {
    "land": "grundstueck-kaufen",
    "apartment": "wohnung-kaufen",
    "house": "haus-kaufen",
}
MAX_PAGES_PER_TYPE = 5
BLOB_PATHNAME = "properties.json"


def scrape_all() -> tuple[list[dict], list[str]]:
    page1_urls = [f"{BASE}/{slug}" for slug in PROPERTY_TYPES.values()]
    log.info("Phase 1: fetching first page of each type")
    page1_html = fetch_html(page1_urls)

    seen: dict[str, dict] = {}
    errors: list[str] = []
    extra_urls: list[str] = []
    extra_url_to_type: dict[str, str] = {}

    for prop_type, slug in PROPERTY_TYPES.items():
        url = f"{BASE}/{slug}"
        html = page1_html.get(url, "")
        if not html:
            errors.append(f"{prop_type}: empty response on page 1")
            continue
        props = parse_search_results(html)
        log.info("  %s page 1: %d listings", prop_type, len(props))
        for p in props:
            p.property_type = prop_type
            seen[p.id] = p.to_dict()

        total = min(parse_total_pages(html), MAX_PAGES_PER_TYPE)
        for page in range(2, total + 1):
            page_url = f"{url}?pagenumber={page}"
            extra_urls.append(page_url)
            extra_url_to_type[page_url] = prop_type

    if extra_urls:
        log.info("Phase 2: fetching %d additional pages", len(extra_urls))
        extra_html = fetch_html(extra_urls)
        for url, html in extra_html.items():
            prop_type = extra_url_to_type[url]
            if not html:
                errors.append(f"{prop_type}: empty response on {url}")
                continue
            props = parse_search_results(html)
            log.info("  %s %s: %d listings", prop_type, url.rsplit("=", 1)[-1], len(props))
            for p in props:
                p.property_type = prop_type
                seen[p.id] = p.to_dict()

    return list(seen.values()), errors


def upload(payload_path: Path) -> str:
    cmd = [
        "vercel", "blob", "put", str(payload_path),
        "--pathname", BLOB_PATHNAME,
        "--access", "public",
        "--allow-overwrite", "true",
        "--content-type", "application/json",
        "--cache-control-max-age", "3600",
    ]
    log.info("Uploading: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        log.error("vercel blob put failed:\n%s\n%s", result.stdout, result.stderr)
        sys.exit(1)
    log.info(result.stdout.strip())
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("https://") and BLOB_PATHNAME in line:
            return line
        if "URL:" in line:
            return line.split("URL:", 1)[1].strip()
    return ""


def main() -> None:
    properties, errors = scrape_all()
    if not properties:
        log.error("No properties scraped — refusing to overwrite blob with empty set")
        if errors:
            log.error("Errors: %s", "; ".join(errors))
        sys.exit(2)

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(properties),
        "errors": errors,
        "properties": properties,
    }

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp_path = Path(f.name)

    try:
        url = upload(tmp_path)
        log.info("Done. %d properties uploaded.", len(properties))
        if url:
            log.info("Public URL: %s", url)
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
