"""Scrape ImmoScout24 + Immowelt with a headless browser and upload the
combined dataset to Vercel Blob.

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
from scraper import immowelt as iw  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("refresh")

IS24_BASE = "https://www.immobilienscout24.de/Suche/de/berlin/berlin"
IS24_SLUGS = {
    "land": "grundstueck-kaufen",
    "apartment": "wohnung-kaufen",
    "house": "haus-kaufen",
}
PROPERTY_TYPES = ("land", "apartment", "house")
MAX_PAGES_PER_TYPE = 20  # per source per type
BLOB_PATHNAME = "properties.json"


def _is24_url(prop_type: str, page: int = 1) -> str:
    slug = IS24_SLUGS[prop_type]
    base = f"{IS24_BASE}/{slug}"
    return base if page == 1 else f"{base}?pagenumber={page}"


def scrape_all() -> tuple[list[dict], list[str]]:
    """Phase 1: fetch page 1 of each type from each source.
    Phase 2: fetch additional pages based on what each source reports.
    """
    seen: dict[str, dict] = {}
    errors: list[str] = []

    # Phase 1 — page 1 from both sources for all 3 types
    page1_urls: list[str] = []
    page1_meta: dict[str, tuple[str, str]] = {}  # url → (source, prop_type)
    for prop_type in PROPERTY_TYPES:
        u = _is24_url(prop_type)
        page1_urls.append(u)
        page1_meta[u] = ("is24", prop_type)
        u = iw.url_for(prop_type)
        page1_urls.append(u)
        page1_meta[u] = ("iw", prop_type)

    log.info("Phase 1: fetching %d first-pages", len(page1_urls))
    page1_html = fetch_html(page1_urls)

    extra_urls: list[str] = []
    extra_meta: dict[str, tuple[str, str]] = {}

    for url, (source, prop_type) in page1_meta.items():
        html = page1_html.get(url, "")
        if not html:
            errors.append(f"{source}/{prop_type}: empty response on page 1")
            continue
        if source == "is24":
            props = parse_search_results(html)
            for p in props:
                p.property_type = prop_type
                seen[p.id] = p.to_dict()
            total = min(parse_total_pages(html), MAX_PAGES_PER_TYPE)
            log.info("  is24/%s page 1: %d listings (%d pages total)", prop_type, len(props), total)
            for page in range(2, total + 1):
                page_url = _is24_url(prop_type, page)
                extra_urls.append(page_url)
                extra_meta[page_url] = ("is24", prop_type)
        else:
            props = iw.parse_listings(html, prop_type)
            for p in props:
                seen[p.id] = p.to_dict()
            total = min(iw.parse_total_pages(html), MAX_PAGES_PER_TYPE)
            log.info("  iw/%s page 1: %d listings (%d pages total)", prop_type, len(props), total)
            for page in range(2, total + 1):
                page_url = iw.url_for(prop_type, page)
                extra_urls.append(page_url)
                extra_meta[page_url] = ("iw", prop_type)

    if not extra_urls:
        return list(seen.values()), errors

    log.info("Phase 2: fetching %d additional pages", len(extra_urls))
    extra_html = fetch_html(extra_urls)

    for url, (source, prop_type) in extra_meta.items():
        html = extra_html.get(url, "")
        if not html:
            errors.append(f"{source}/{prop_type}: empty response on {url}")
            continue
        if source == "is24":
            props = parse_search_results(html)
            for p in props:
                p.property_type = prop_type
                seen[p.id] = p.to_dict()
            log.info("  is24/%s %s: %d", prop_type, url.rsplit("=", 1)[-1], len(props))
        else:
            props = iw.parse_listings(html, prop_type)
            for p in props:
                seen[p.id] = p.to_dict()
            page_n = url.rsplit("page=", 1)[-1] if "page=" in url else "?"
            log.info("  iw/%s page=%s: %d", prop_type, page_n, len(props))

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
