from app.schemas.search import SearchCandidate


class FakeSearchClient:
    def __init__(self, candidates: list[SearchCandidate]) -> None:
        self._candidates = candidates
        self.queries: list[str] = []

    def search(self, query: str) -> list[SearchCandidate]:
        self.queries.append(query)
        return self._candidates
