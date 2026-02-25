import webbrowser
from pydantic import BaseModel, Field, HttpUrl

class OpenLinksIn(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=20)

class OpenLinksTool:
    name = "open_links"
    InputModel = OpenLinksIn
    risk = "LOW"

    def validate(self, data: dict) -> OpenLinksIn:
        return self.InputModel.model_validate(data)

    def run(self, validated: OpenLinksIn) -> dict:
        opened = []
        for u in validated.urls:
            webbrowser.open(str(u))
            opened.append(str(u))
        return {"opened": opened}