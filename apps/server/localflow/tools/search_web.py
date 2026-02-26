from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import httpx
from pydantic import BaseModel, Field


class SearchWebIn(BaseModel):
    query: str = Field(min_length=2, max_length=300)
    max_results: int = Field(default=5, ge=1, le=10)
    allowed_domains: list[str] | None = Field(default=None, max_length=20)


class SearchWebTool:
    name = "search_web"
    InputModel = SearchWebIn
    risk = "LOW"

    def validate(self, data: dict) -> SearchWebIn:
        return self.InputModel.model_validate(data)

    def _domain_allowed(self, url: str, allowed_domains: list[str] | None) -> bool:
        if not allowed_domains:
            return True

        host = (urlparse(url).hostname or "").lower().strip(".")
        if not host:
            return False

        normalized = [d.lower().strip(".") for d in allowed_domains if d and d.strip()]
        return any(host == d or host.endswith("." + d) for d in normalized)

    def _extract_google_links(self, html: str) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for raw in re.findall(r'href="(/url\?q=[^"]+)"', html):
            parsed = urlparse(raw)
            q = parse_qs(parsed.query).get("q", [])
            if not q:
                continue
            target = q[0]
            if not target.startswith("http"):
                continue
            if target in seen:
                continue
            seen.add(target)
            links.append(target)
        return links

    def run(self, validated: SearchWebIn) -> dict[str, Any]:
        url = (
            "https://www.google.com/search"
            f"?q={quote_plus(validated.query)}"
            f"&num={validated.max_results}"
            "&hl=en"
            "&pws=0"
            "&safe=active"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        response = httpx.get(url, headers=headers, timeout=15.0)
        response.raise_for_status()
        results: list[dict[str, str]] = []
        for link in self._extract_google_links(response.text):
            if not self._domain_allowed(link, validated.allowed_domains):
                continue
            host = urlparse(link).hostname or link
            results.append({"title": host, "url": link})
            if len(results) >= validated.max_results:
                break

        return {"query": validated.query, "results": results}
