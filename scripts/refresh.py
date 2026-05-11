"""Scrape ImmoScout24 + Immowelt with a headless browser, merge the result
with the previously-uploaded dataset, and upload to Vercel Blob.

Run locally (datacenter IPs are blocked, AWS WAF requires a real browser).
Designed to be run by launchd daily.

The blob is *cumulative*: each listing carries `first_seen` and `last_seen`
ISO timestamps. Listings re-seen in a refresh have their `last_seen`
advanced and their fields refreshed (e.g. price changes). Listings missing
from this run are kept in place. Listings whose `last_seen` is older than
RETENTION_DAYS are pruned at upload time.

Reads no env vars; relies on the local `vercel` CLI being authenticated.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scraper.browser_fetch import fetch_html  # noqa: E402
from scraper.parser import parse_search_results, parse_total_pages  # noqa: E402
from scraper import immowelt as iw  # noqa: E402
from scraper import kleinanzeigen as ka  # noqa: E402

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
MAX_PAGES_PER_TYPE = 100  # per source per type (capped by what each source actually paginates)
BLOB_PATHNAME = "properties.json"
BLOB_PUBLIC_URL = "https://5dxkyfjiib2tfjbl.public.blob.vercel-storage.com/properties.json"
RETENTION_DAYS = 60  # drop listings not seen in this many days
HISTORY_PATH = PROJECT_ROOT / "scripts" / "refresh_history.jsonl"


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

    if extra_urls:
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

    # Phase 3 — Kleinanzeigen via plain HTTP (no bot protection, ~0.5s per page).
    log.info("Phase 3: Kleinanzeigen")
    ka_page1_urls = [ka.url_for(t, 1) for t in ka.PROPERTY_TYPES]
    ka_html_p1 = ka.fetch_pages(ka_page1_urls)
    ka_extra_urls: list[str] = []
    ka_extra_meta: dict[str, str] = {}
    for prop_type, page1_url in zip(ka.PROPERTY_TYPES, ka_page1_urls):
        html = ka_html_p1.get(page1_url, "")
        if not html:
            errors.append(f"ka/{prop_type}: empty response on page 1")
            continue
        props = ka.parse_listings(html, prop_type)
        log.info("  ka/%s page 1: %d", prop_type, len(props))
        for p in props:
            seen[p.id] = p.to_dict()
        total = min(ka.parse_total_pages(html), MAX_PAGES_PER_TYPE)
        for page in range(2, total + 1):
            u = ka.url_for(prop_type, page)
            ka_extra_urls.append(u)
            ka_extra_meta[u] = prop_type
    if ka_extra_urls:
        ka_html_extra = ka.fetch_pages(ka_extra_urls)
        for url, prop_type in ka_extra_meta.items():
            html = ka_html_extra.get(url, "")
            if not html:
                continue
            props = ka.parse_listings(html, prop_type)
            for p in props:
                seen[p.id] = p.to_dict()
            page_n = url.rsplit("seite:", 1)[-1].split("/")[0] if "seite:" in url else "?"
            log.info("  ka/%s page=%s: %d", prop_type, page_n, len(props))

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


def fetch_existing() -> dict[str, dict]:
    """Pull the current blob (if any) so this run can merge into it."""
    try:
        with urllib.request.urlopen(BLOB_PUBLIC_URL, timeout=15) as resp:
            payload = json.load(resp)
    except Exception as e:
        log.warning("No existing blob to merge with (%s) — starting fresh", e)
        return {}
    raw = payload.get("properties", []) if isinstance(payload, dict) else []
    by_id: dict[str, dict] = {}
    for item in raw:
        if isinstance(item, dict) and item.get("id"):
            by_id[item["id"]] = item
    log.info("Loaded %d existing listings from blob for merge", len(by_id))
    return by_id


def merge(existing: dict[str, dict], scraped: list[dict], now_iso: str) -> tuple[list[dict], dict]:
    """Merge fresh listings into the existing dict, stamping first/last seen.
    Drop listings older than RETENTION_DAYS that weren't re-seen.
    """
    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).isoformat()
    fresh_ids = {p["id"] for p in scraped if p.get("id")}
    merged: dict[str, dict] = {}

    new_count = 0
    refreshed_count = 0
    kept_count = 0
    pruned_count = 0

    # Carry forward existing listings, possibly refreshed
    for pid, prev in existing.items():
        if pid in fresh_ids:
            continue  # will be handled in the scraped loop below
        last_seen = prev.get("last_seen") or prev.get("first_seen")
        if last_seen and last_seen < cutoff_iso:
            pruned_count += 1
            continue
        merged[pid] = prev
        kept_count += 1

    # Apply scraped listings (new or refreshed)
    for p in scraped:
        pid = p.get("id")
        if not pid:
            continue
        prev = existing.get(pid)
        if prev:
            entry = dict(p)
            entry["first_seen"] = prev.get("first_seen") or now_iso
            entry["last_seen"] = now_iso
            refreshed_count += 1
        else:
            entry = dict(p)
            entry["first_seen"] = now_iso
            entry["last_seen"] = now_iso
            new_count += 1
        merged[pid] = entry

    stats = {
        "new": new_count,
        "refreshed": refreshed_count,
        "kept_archived": kept_count,
        "pruned": pruned_count,
    }
    return list(merged.values()), stats


def main() -> None:
    existing = fetch_existing()

    scraped, errors = scrape_all()
    if not scraped:
        log.error("No properties scraped — refusing to touch blob")
        if errors:
            log.error("Errors: %s", "; ".join(errors))
        sys.exit(2)

    now_iso = datetime.now(timezone.utc).isoformat()
    properties, stats = merge(existing, scraped, now_iso)
    log.info("Merge: %d new, %d refreshed, %d kept (archived), %d pruned",
             stats["new"], stats["refreshed"], stats["kept_archived"], stats["pruned"])

    payload = {
        "updated_at": now_iso,
        "count": len(properties),
        "errors": errors,
        "scrape_stats": stats,
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
        # Append a single summary line to the history file (append-only,
        # so cron + manual runs accumulate over time).
        try:
            with HISTORY_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": now_iso,
                    "total": len(properties),
                    "new": stats["new"],
                    "refreshed": stats["refreshed"],
                    "kept_archived": stats["kept_archived"],
                    "pruned": stats["pruned"],
                    "errors": len(errors),
                }) + "\n")
        except OSError as e:
            log.warning("could not write history: %s", e)
    finally:
        tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
