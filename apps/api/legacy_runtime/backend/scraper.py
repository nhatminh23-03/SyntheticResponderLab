"""Lightweight product page scraper for extracting text content from URLs."""

from __future__ import annotations

import re

import requests


def scrape_product_page(url: str, timeout: int = 15) -> str:
    """Fetch a URL and return cleaned text content.

    Strips HTML tags, scripts, styles, and excess whitespace.
    Raises ``RuntimeError`` on fetch failures.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Failed to fetch URL: {exc}") from exc

    if resp.status_code != 200:
        raise RuntimeError(f"URL returned HTTP {resp.status_code}")

    html = resp.text

    # Remove script and style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&nbsp;", " ").replace("&quot;", '"').replace("&#39;", "'")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Truncate to ~8000 chars to stay within LLM context limits
    if len(text) > 8000:
        text = text[:8000]

    return text
