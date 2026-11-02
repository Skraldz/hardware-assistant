"""Measures how much of Ollama's context window an extraction call actually uses.

Why this exists: `OllamaClient` did not set `num_ctx`, so Ollama used its own
default (2048 in older builds, 4096 in current ones). Ollama does not fail
loudly on overflow -- it silently drops the oldest tokens, which for this
prompt means dropping the *page text* the whole web-lookup feature exists to
provide. The model then "misses" fields that were right there, and it looks
like a model-capability problem when it is a configuration problem.

Two modes:

  python -m scripts.measure_prompt_budget
      Static: rebuilds the real prompts and measures them. Needs nothing
      running -- no Ollama, no database.

  python -m scripts.measure_prompt_budget --live
      Also calls a running Ollama twice per category (at the old default and
      at the configured num_ctx) and counts how many spec fields come back
      non-null. Needs Ollama up.

Token figures are estimates: no tokenizer for qwen2.5 is installed, so this
reports a range over plausible chars-per-token ratios. Character counts are
exact, and the conclusion holds across the whole range.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.enums import Category  # noqa: E402
from app.llm.prompts import (  # noqa: E402
    CATEGORY_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    build_category_prompt,
    build_extract_prompt,
)
from app.schemas.components import EXTRACT_SCHEMA_BY_CATEGORY  # noqa: E402

# Spec pages are dense with numbers, units and model names, which tokenize
# worse than prose. 4.0 is a generous upper bound, 3.0 a realistic lower one.
CHARS_PER_TOKEN = (3.0, 3.5, 4.0)

OLLAMA_DEFAULT_CTX_OLD = 2048
OLLAMA_DEFAULT_CTX_NEW = 4096

# A stand-in for one fetched product page, padded to exactly the cap the code
# enforces (settings.page_fetch_max_chars) so the measurement reflects the
# worst case the pipeline can actually produce, not a lucky short page.
_PAGE_SEED = (
    "NVIDIA GeForce RTX 4070 Ti SUPER Specifications. Graphics Processor AD103. "
    "Architecture Ada Lovelace. Process Size 5 nm. Transistors 45,900 million. "
    "Die Size 379 mm2. Released Jan 24th, 2024. Generation GeForce 40. "
    "Bus Interface PCIe 4.0 x16. Memory Size 16 GB. Memory Type GDDR6X. "
    "Memory Bus 256 bit. Bandwidth 672.3 GB/s. Shading Units 8448. TMUs 264. "
    "ROPs 112. Tensor Cores 264. RT Cores 66. L1 Cache 128 KB per SM. "
    "L2 Cache 48 MB. Base Clock 2340 MHz. Boost Clock 2610 MHz. "
    "Memory Clock 1313 MHz 21 Gbps effective. TDP 285 W. "
    "Suggested PSU 700 W. Outputs 1x HDMI 2.1a, 3x DisplayPort 1.4a. "
    "Power Connectors 1x 16-pin. Board Length 267 mm, 10.5 inches. "
    "Board Width 112 mm, 4.4 inches. Slot Width Triple-slot. "
)


def page_text(n_chars: int) -> str:
    repeats = (n_chars // len(_PAGE_SEED)) + 1
    return (_PAGE_SEED * repeats)[:n_chars]


def estimate_tokens(chars: int) -> tuple[int, int]:
    """(low, high) token estimate -- low from the most generous ratio."""
    return (round(chars / CHARS_PER_TOKEN[2]), round(chars / CHARS_PER_TOKEN[0]))


def build_web_snippet(page: str) -> str:
    """Reproduces routers/components.py::extract_component_specs exactly:
    the chosen candidate's fetched page text, then the other four search
    results as short previews."""
    others = "\n\n".join(
        f"GeForce RTX 4070 Ti SUPER review {i}\n"
        f"Our full review of the RTX 4070 Ti SUPER, with benchmarks across 25 games, "
        f"thermals, acoustics and power measurements at stock and overclocked settings."
        for i in range(1, 5)
    )
    if not page:
        return others
    return (
        f'Full page content for "GeForce RTX 4070 Ti SUPER Specs":\n{page}\n\n'
        f"--- Other search results (short previews only) ---\n{others}"
    )


def measure(label: str, system: str, prompt: str, schema_json: str) -> dict:
    sys_chars, prompt_chars = len(system), len(prompt)
    total = sys_chars + prompt_chars
    lo, hi = estimate_tokens(total)
    return {
        "label": label,
        "system_chars": sys_chars,
        "prompt_chars": prompt_chars,
        "total_chars": total,
        "schema_chars": len(schema_json),
        "tokens_low": lo,
        "tokens_high": hi,
    }


def static_report() -> None:
    settings = get_settings()
    cap = settings.page_fetch_max_chars
    page = page_text(cap)
    snippet_full = build_web_snippet(page)
    snippet_none = build_web_snippet("")

    print(f"page_fetch_max_chars = {cap}")
    print(f"configured ollama_num_ctx = {getattr(settings, 'ollama_num_ctx', '(not set)')}")
    print()

    rows = []
    for cat in (Category.GPU, Category.MOTHERBOARD, Category.CPU):
        schema = EXTRACT_SCHEMA_BY_CATEGORY[cat]
        schema_json = json.dumps(schema.model_json_schema())
        rows.append(
            measure(
                f"extract/{cat.value} (page fetched)",
                EXTRACT_SYSTEM_PROMPT,
                build_extract_prompt("GeForce RTX 4070 Ti SUPER", cat.value, web_snippet=snippet_full),
                schema_json,
            )
        )
    rows.append(
        measure(
            "extract/gpu (snippets only, no page)",
            EXTRACT_SYSTEM_PROMPT,
            build_extract_prompt("GeForce RTX 4070 Ti SUPER", "gpu", web_snippet=snippet_none),
            json.dumps(EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU].model_json_schema()),
        )
    )
    rows.append(
        measure(
            "category guess (page fetched)",
            CATEGORY_SYSTEM_PROMPT,
            build_category_prompt("GeForce RTX 4070 Ti SUPER", web_snippet=snippet_full),
            "",
        )
    )

    head = f"{'call':<40}{'chars':>8}{'est. tokens':>16}   vs 2048   vs 4096"
    print(head)
    print("-" * len(head))
    for r in rows:
        lo, hi = r["tokens_low"], r["tokens_high"]
        v2 = (
            "OVERFLOW"
            if lo > OLLAMA_DEFAULT_CTX_OLD
            else ("risky" if hi > OLLAMA_DEFAULT_CTX_OLD else "fits")
        )
        v4 = (
            "OVERFLOW"
            if lo > OLLAMA_DEFAULT_CTX_NEW
            else ("risky" if hi > OLLAMA_DEFAULT_CTX_NEW else "fits")
        )
        print(f"{r['label']:<40}{r['total_chars']:>8}{f'{lo}-{hi}':>16}{v2:>11}{v4:>9}")

    print()
    print("'risky' = fits only at the most generous tokens-per-char ratio.")
    print("The JSON schema is passed as Ollama's `format` and constrains sampling;")
    print("it is not prepended to the prompt, so it is excluded from the counts above.")
    print("Output tokens (the JSON object the model writes) still come out of num_ctx:")
    print("  a full GPU spec object is roughly 100-200 tokens on top of the prompt.")


def live_report() -> None:
    from app.llm.client import LLMUnavailableError, OllamaClient

    settings = get_settings()
    page = page_text(settings.page_fetch_max_chars)
    snippet = build_web_snippet(page)
    schema = EXTRACT_SCHEMA_BY_CATEGORY[Category.GPU]
    prompt = build_extract_prompt("GeForce RTX 4070 Ti SUPER", "gpu", web_snippet=snippet)

    print(f"model = {settings.ollama_model}  base_url = {settings.ollama_base_url}")
    print(f"{'num_ctx':>10}{'fields non-null':>18}{'  values'}")
    print("-" * 70)

    for ctx in (OLLAMA_DEFAULT_CTX_OLD, OLLAMA_DEFAULT_CTX_NEW, settings.ollama_num_ctx):
        client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            timeout=settings.ollama_request_timeout_s,
            num_ctx=ctx,
        )
        try:
            raw = client.generate_structured(system=EXTRACT_SYSTEM_PROMPT, prompt=prompt, schema=schema)
            data = json.loads(raw)
        except (LLMUnavailableError, ValueError) as exc:
            print(f"{ctx:>10}{'ERROR':>18}  {exc}")
            continue
        filled = {k: v for k, v in data.items() if v is not None}
        total = len(schema.model_fields)
        print(f"{ctx:>10}{f'{len(filled)}/{total}':>18}  {json.dumps(filled, ensure_ascii=False)[:160]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="also call a running Ollama")
    args = parser.parse_args()
    static_report()
    if args.live:
        print()
        print("=" * 70)
        live_report()


if __name__ == "__main__":
    main()
