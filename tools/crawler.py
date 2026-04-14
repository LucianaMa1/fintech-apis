"""
Crawler Tool — Web page discovery and content extraction.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger("tool.crawl")

PAGE_PATTERNS = {
    "pricing": ["/pricing", "/plans"],
    "docs": ["/docs", "/documentation", "/reference", "/api"],
    "sdks": ["/docs/sdks", "/docs/libraries", "/docs/quickstart", "/sdks"],
    "features": ["/features", "/products", "/capabilities"],
    "compliance": ["/security", "/compliance", "/trust"],
    "spec": [
        "/openapi.json", "/openapi.yaml", "/swagger.json",
        "/api/openapi.json", "/api/v1/openapi.json",
    ],
}

MAX_TEXT = 12_000


class CrawlerTool:
    """Discovers and crawls relevant pages for an API provider."""

    def __init__(self, max_pages: int = 25):
        self.max_pages = max_pages

    async def run(
        self,
        website: str,
        docs_url: str,
        use_playwright: bool = False,
    ) -> list[dict]:
        """
        Crawl a provider's website and docs.
        Returns list of page dicts with url, title, text, content_hash.
        """
        seen = set()
        pages = []

        # Build candidate URLs
        candidates = [website.rstrip("/"), docs_url.rstrip("/")]
        for base in [website, docs_url]:
            base = base.rstrip("/")
            for purpose, paths in PAGE_PATTERNS.items():
                for path in paths:
                    candidates.append(f"{base}{path}")

        # Deduplicate
        candidates = list(dict.fromkeys(candidates))[:self.max_pages]

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": "APIIntelAgent/1.0"},
        ) as client:
            for url in candidates:
                if url in seen:
                    continue
                seen.add(url)

                page = await self._fetch(client, url, use_playwright)
                if page:
                    pages.append(page)

        log.info(f"Crawled {len(pages)}/{len(candidates)} pages")
        return pages

    async def _fetch(
        self, client: httpx.AsyncClient, url: str, use_playwright: bool = False
    ) -> Optional[dict]:
        try:
            if use_playwright:
                return await self._fetch_playwright(url)

            resp = await client.get(url)
            if resp.status_code != 200:
                return None

            ct = resp.headers.get("content-type", "")
            is_spec = url.endswith((".json", ".yaml")) or "json" in ct

            if is_spec:
                text = resp.text[:MAX_TEXT]
                return {
                    "url": url,
                    "title": "[OpenAPI Spec]",
                    "text": text,
                    "content_hash": hashlib.md5(text.encode()).hexdigest(),
                    "is_spec": True,
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                }

            title, text = self._clean(resp.text)
            if len(text.strip()) < 50:
                return None

            return {
                "url": url,
                "title": title,
                "text": text,
                "content_hash": hashlib.md5(text.encode()).hexdigest(),
                "is_spec": False,
                "crawled_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            log.debug(f"Failed: {url} — {e}")
            return None

    async def _fetch_playwright(self, url: str) -> Optional[dict]:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.warning("Playwright not available, skipping")
            return None

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=15000)
                html = await page.content()
                title, text = self._clean(html)
                if len(text.strip()) < 50:
                    return None
                return {
                    "url": url,
                    "title": title,
                    "text": text,
                    "content_hash": hashlib.md5(text.encode()).hexdigest(),
                    "is_spec": False,
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                }
            finally:
                await browser.close()

    def _clean(self, html: str) -> tuple[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return title, text[:MAX_TEXT]
