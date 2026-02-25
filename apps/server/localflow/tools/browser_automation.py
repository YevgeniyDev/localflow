from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class BrowserAction(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    type: Literal["goto", "click", "fill", "press", "wait_for"]
    selector: str | None = Field(default=None, max_length=500)
    value: str | None = Field(default=None, max_length=4000)
    url: HttpUrl | None = None
    timeout_ms: int = Field(default=10000, ge=100, le=120000)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "BrowserAction":
        if self.type == "goto" and self.url is None:
            raise ValueError("goto action requires url")
        if self.type in {"click", "fill", "wait_for"} and not (self.selector or "").strip():
            raise ValueError(f"{self.type} action requires selector")
        if self.type in {"fill", "press"} and self.value is None:
            raise ValueError(f"{self.type} action requires value")
        return self


class BrowserAutomationIn(BaseModel):
    start_url: HttpUrl | None = None
    actions: list[BrowserAction] = Field(min_length=1, max_length=20)
    headless: bool = True
    dry_run: bool = True


class BrowserAutomationTool:
    name = "browser_automation"
    InputModel = BrowserAutomationIn
    risk = "HIGH"

    def validate(self, data: dict) -> BrowserAutomationIn:
        return self.InputModel.model_validate(data)

    def run(self, validated: BrowserAutomationIn) -> dict:
        if validated.dry_run:
            return {
                "dry_run": True,
                "start_url": str(validated.start_url) if validated.start_url else None,
                "actions": [a.model_dump(mode="json") for a in validated.actions],
            }

        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Playwright is not installed. Install 'playwright' and browser binaries.") from e

        step_log: list[dict] = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=validated.headless)
            page = browser.new_page()
            try:
                if validated.start_url:
                    page.goto(str(validated.start_url), wait_until="domcontentloaded")
                    step_log.append({"event": "start_url", "url": page.url})

                for action in validated.actions:
                    if action.type == "goto":
                        page.goto(str(action.url), timeout=action.timeout_ms, wait_until="domcontentloaded")
                    elif action.type == "click":
                        page.click(action.selector or "", timeout=action.timeout_ms)
                    elif action.type == "fill":
                        page.fill(action.selector or "", action.value or "", timeout=action.timeout_ms)
                    elif action.type == "press":
                        page.keyboard.press(action.value or "")
                    elif action.type == "wait_for":
                        page.wait_for_selector(action.selector or "", timeout=action.timeout_ms)

                    step_log.append({"id": action.id, "type": action.type, "url": page.url})

                return {"dry_run": False, "final_url": page.url, "steps": step_log}
            finally:
                browser.close()
