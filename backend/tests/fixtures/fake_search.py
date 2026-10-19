from app.schemas.search import SearchCandidate
from app.search.client import SearchUnavailableError


class FakeSearchClient:
    def __init__(self, candidates: list[SearchCandidate], *, unavailable: bool = False) -> None:
        self._candidates = candidates
        self._unavailable = unavailable
        self.queries: list[str] = []

    def search(self, query: str) -> list[SearchCandidate]:
        self.queries.append(query)
        if self._unavailable:
            raise SearchUnavailableError("Simuleret: SearXNG kan ikke nås")
        return self._candidates
