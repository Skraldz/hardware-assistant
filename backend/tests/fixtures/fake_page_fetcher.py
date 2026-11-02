"""A fake PageFetcher that never makes a real HTTP request (SPEC.md §9.1)."""


class FakePageFetcher:
    def __init__(self, text: str | None = None) -> None:
        self.text = text
        self.fetched_urls: list[str] = []

    def fetch(self, url: str) -> str | None:
        self.fetched_urls.append(url)
        return self.text
