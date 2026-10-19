"""A fake LLMClient that returns canned responses from tests/fixtures/
instead of calling Ollama (SPEC.md §9.1). Responses are consumed in order,
so a test can simulate "invalid, then valid on retry" by queueing two
fixtures.
"""

from pathlib import Path

from pydantic import BaseModel

FIXTURES_DIR = Path(__file__).parent / "llm_responses"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def generate_structured(self, *, system: str, prompt: str, schema: type[BaseModel]) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            raise AssertionError("FakeLLMClient has no more queued responses")
        return self._responses.pop(0)

    def ping(self) -> bool:
        return True
