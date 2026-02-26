from __future__ import annotations

from urllib.parse import parse_qs, quote_plus, urljoin, urlparse

from pydantic import BaseModel, Field


class BrowserSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=10)
    headless: bool = True


class BrowserSearchTool:
    name = "browser_search"
    InputModel = BrowserSearchIn
    risk = "MEDIUM"

    def validate(self, data: dict) -> BrowserSearchIn:
        return self.InputModel.model_validate(data)

    def _normalize_query(self, query: str) -> str:
        q = (query or "").strip()
        # Remove common imperative wrappers so search intent is cleaner.
        prefixes = [
            "open ",
            "find ",
            "search ",
            "look up ",
            "please open ",
            "please find ",
            "please search ",
        ]
        lowered = q.lower()
        for p in prefixes:
            if lowered.startswith(p):
                q = q[len(p):].strip()
                lowered = q.lower()
                break
        q = q.replace("'s linkedin", " linkedin").replace(" profile", " ").strip()
        return " ".join(q.split())

    def _extract_target_url(self, href: str) -> str | None:
        if not href:
            return None
        if href.startswith("/url?"):
            parsed = urlparse(href)
            q = parse_qs(parsed.query).get("q", [])
            if q and q[0].startswith("http"):
                return q[0]
            return None
        absolute = urljoin("https://www.google.com", href)
        if absolute.startswith("http"):
            return absolute
        return None

    def run(self, validated: BrowserSearchIn) -> dict:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Playwright is not installed. Install 'playwright' and browser binaries.") from e

        normalized_query = self._normalize_query(validated.query)
        query_url = (
            "https://www.google.com/search"
            f"?q={quote_plus(normalized_query)}"
            f"&num={validated.max_results}"
            "&hl=en"
            "&pws=0"
            "&safe=active"
        )

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=validated.headless)
            page = browser.new_page()
            try:
                page.goto(query_url, wait_until="domcontentloaded")
                anchors = page.query_selector_all("a")
                for anchor in anchors:
                    href = anchor.get_attribute("href") or ""
                    target = self._extract_target_url(href)
                    if not target:
                        continue
                    if target in seen:
                        continue
                    host = (urlparse(target).hostname or "").lower()
                    if host.endswith("google.com") or host.endswith("googleusercontent.com"):
                        continue
                    text = (anchor.inner_text() or "").strip()
                    seen.add(target)
                    results.append({"title": text or host or target, "url": target})
                    if len(results) >= validated.max_results:
                        break
            finally:
                browser.close()

        return {
            "query": validated.query,
            "normalized_query": normalized_query,
            "engine": "google",
            "results": results,
        }
