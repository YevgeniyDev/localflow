from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

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

    def run(self, validated: SearchWebIn) -> dict[str, Any]:
        params = {
            "q": validated.query,
            "format": "json",
            "no_html": "1",
            "no_redirect": "1",
        }
        response = httpx.get("https://api.duckduckgo.com/", params=params, timeout=15.0)
        response.raise_for_status()
        data = response.json()

        results: list[dict[str, str]] = []

        for item in data.get("RelatedTopics", []):
            if isinstance(item, dict) and isinstance(item.get("Topics"), list):
                candidates = item.get("Topics", [])
            else:
                candidates = [item]

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                url = candidate.get("FirstURL")
                text = candidate.get("Text")
                if not isinstance(url, str) or not isinstance(text, str):
                    continue
                if not self._domain_allowed(url, validated.allowed_domains):
                    continue
                results.append({"title": text, "url": url})
                if len(results) >= validated.max_results:
                    return {"query": validated.query, "results": results}

        abstract_url = data.get("AbstractURL")
        abstract_text = data.get("AbstractText")
        if (
            isinstance(abstract_url, str)
            and isinstance(abstract_text, str)
            and self._domain_allowed(abstract_url, validated.allowed_domains)
            and len(results) < validated.max_results
        ):
            results.append({"title": abstract_text, "url": abstract_url})

        return {"query": validated.query, "results": results}
