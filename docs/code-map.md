# Code map — a reading order

`architecture.md` explains how the services fit together. This is the
companion for reading the code itself: which file to open, in what order,
and the one question each answers. Every module, class and function has a
docstring, so this only has to get you to the right file.

Roughly 3,600 of the backend's ~8,200 lines are `app/seed.py`, which is a
list of 210 hardware components and nothing else. Skip it.

---

## Read these six, in this order (~1,700 lines)

That is the whole system. Everything else is plumbing around it.

### 1. `app/compatibility/types.py` — the vocabulary (126 lines)

Start here or nothing else makes sense. Four small classes: `Build` (one
component per slot), `RuleResult` (**pass / fail / unknown**, with a reason),
`BuildEvaluation`, `EngineResult`.

The three-way status is the single most important design decision in the
project. A missing specification is not the same as an incompatibility: the
build is still offered, with the gap shown as a warning, rather than being
rejected on data the user never entered.

### 2. `app/compatibility/rules.py` — where compatibility is actually decided (426 lines)

Sixteen pure functions, each `(Build) -> RuleResult`, each independent and
readable on its own. No AI anywhere in this file. Read three or four, then
skim — they all have the same shape.

`ALL_RULES` at the bottom is the list the engine runs. It is the only source
of truth for "how many rules are there"; the prose elsewhere does not read
it, so it can drift.

### 3. `app/compatibility/engine.py` — combining candidates into builds (190 lines)

`generate_builds` is the nest of loops that forms combinations and keeps
only those where no rule says fail. `top_n` bounds the combinatorics, and the
early-prune comments explain why some combinations are skipped before being
evaluated at all.

Note what it does *not* do: it takes candidates in the order it is given and
never reorders them. Ranking is the caller's job — which is exactly where a
real bug lived.

### 4. `app/pipeline/recommend.py` — the heart (868 lines)

The longest file worth reading and the one with the most history in it. Read
`recommend()` at the bottom first for the shape, then work upward into the
helpers. The sequence is fixed function calls, not agentic tool-calling:

```
interpret_requirements   (LLM)   free text -> ProjectRequirements
prefilter_candidates     (code)  drop out-of-stock, faulty, hard-requirement failures; rank the rest
generate_builds          (code)  the engine, above
_select_diverse_builds   (code)  pick a pool spanning distinct CPUs and GPUs
rank_builds              (LLM)   order them, rejecting invented build ids
_to_build_result         (code)  re-verify before showing
generate_chat_reply      (LLM)   write the answer
```

Four functions here are worth reading closely, because each exists because
something went wrong:

- `_validate_requirements` — rejects an era bound that contradicts itself.
- `_sort_candidates_by_relevance` — why sorting each category independently
  produced "no compatible builds" on an inventory that had an obvious answer.
- `_select_diverse_builds` — used twice, and the docstring says why both
  passes are needed.
- `deterministic_score` — the fallback ranking, and the one place with
  always-on nudges that the user never asked for.

### 5. `app/llm/parsing.py` — how a bad AI answer is contained (89 lines)

The smallest important file in the project. `call_llm_with_retry`: validate
against the schema, retry once with the validation error fed back, otherwise
fall back. The `validate` hook is how callers add checks a JSON schema cannot
express — rejecting a hallucinated build id, or a self-contradictory
requirement.

Everything the model produces passes through here.

### 6. `app/llm/prompts.py` — what the model is actually asked (348 lines)

Long but linear. `_data_block` is the one to understand: everything the user
typed and everything fetched from the web is wrapped and labelled as *data,
not instructions* — the OWASP mitigation for indirect prompt injection.

---

## The rest, by the question it answers

| Question | File |
|---|---|
| What is stored? | `app/models.py`, `app/schemas/components.py` |
| What does the API accept and return? | `app/schemas/`, then `app/routers/` |
| How does a component get looked up online? | `app/routers/components.py` (`extract_component_specs`), `app/search/` |
| How is Ollama called? | `app/llm/client.py` |
| How does backup/restore stay trustworthy? | `app/services/backup.py` |
| Where do backups go? | `app/storage/` (`base.py` is the Protocol both backends implement) |
| How is it configured? | `app/config.py`, `.env.example` |
| Why is there no migration tool? | `app/bootstrap.py` |

## Reading the tests instead

`backend/tests/` is often the faster route to "what does this actually do".
Each test file mirrors a module, and the regression tests carry the clearest
statements of intent in the repo — every bug found in a running deployment
has a test whose docstring says what went wrong and why the test would have
caught it.

`tests/test_rules.py` is the one to read first: pass, fail and unknown for
every rule, which is the compatibility model stated as examples.

## Where the history is

`docs/ai-log.md` is the development log, newest first — what was generated,
what was assumed, what broke, and what the tests cover. The entries about
`num_ctx`, the inverted era bound, and the measurement that could not fail
are the ones worth reading before explaining this project to anyone.
