# CLAUDE.md — Hardware Assistant

This file is read automatically by Claude Code. The full technical spec lives in **SPEC.md**, and it must be read before writing code.

## Project in short
Exam project for the elective **Programmering og AI** ("Programming and AI", Zealand, IT-Teknolog, 3rd semester, instructor Zuhair Haroon Khan). The application is an AI-driven hardware assistant and inventory system:
- The user registers their own PC components in a database (MariaDB).
- The user describes a project in free text, e.g. *"headless pc for local AI"*.
- A local LLM (Ollama) interprets the requirement, deterministic Python code verifies compatibility, and the LLM ranks and justifies the valid builds.
- The inventory can be backed up locally or to Azure Blob Storage. Selected via `.env` (`BACKUP_BACKEND=local|azure`).

Stack: Docker Compose, Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Ollama, MariaDB, and a minimal React frontend. SearXNG is optional.

## Problem statement

> The problem statement below is a working English translation. The version actually submitted to and approved by the instructor (zukh@zealand.dk) was written and approved in Danish — see `docs/exam-requirements.md` for the exam's own requirements. This translation exists for the student's own reading comfort; if the two ever diverge, the approved Danish version is authoritative for exam purposes.

**Main question:** How can a Python application be developed that, using a local language model, can assemble a compatible PC configuration from the user's own hardware inventory and a free-text project description? And how can AI tools be used in the development itself, while safeguarding the quality of both the generated code and the model's suggestions?

**Sub-questions:**
1. How is the inventory modeled in a database so that component properties can be used for automatic compatibility checking?
2. How does a local LLM translate free text into structured requirements, and how is that output validated (Pydantic and rule-based verification) so hallucinated or incompatible suggestions are rejected?
3. How is AI used as a programming assistant, what errors were found in AI-generated code, and how were they fixed?
4. How do unit tests secure the compatibility rules, data validation, and handling of invalid AI output?
5. How is data uploaded to the cloud (Azure), and what data-security and responsible-AI-use considerations are relevant?

**Scope boundaries:** Desktop and server PC components only. No prices or purchasing. The LLM interprets and ranks, while compatibility is always decided by code. The frontend is secondary.

## Exam requirements that affect the code
- The learning objectives weight: **AI as a development tool**, **assessing and improving AI-generated code**, **unit tests**, **quality assurance**, and **critical and responsible use of AI**.
- Formal requirement: the application must be able to **upload data to the cloud** (Azure preferred, localhost accepted).
- The report is at most 5 standard pages (12,000 characters). Code and appendices don't count toward that. The code and `docs/ai-log.md` are therefore what documents the work.
- Oral exam: 5 min presentation and 5 min examination. The whole flow must be demonstrable quickly.

## Working rules for Claude Code
1. **Work phase by phase** per SPEC.md §11. **Stop after each phase**, summarize what was done, and wait for review before the next phase.
2. **Update `docs/ai-log.md` after each phase** (format in SPEC.md §10). Be honest about assumptions, uncertainties, and weak points. The "Review" field is filled in by the student themselves. Leave it empty.
3. Small, focused commits per feature with descriptive commit messages.
4. No test may require Ollama, MariaDB, or Azure. Use fakes, mocks, SQLite, and `LocalStorage`.
5. Run `ruff check`, `ruff format`, and `pytest` before declaring a phase done.
6. Code, identifiers, docstrings, UI text, and all project documentation (`docs/`, README, ai-log, this file) are written in English, per the student's explicit request — not the Danish originally planned. The original source documents this project is built from (`SPEC.md`, and the instructor's course materials referenced in `docs/exam-requirements.md`) remain in their original Danish; only the project's own generated code, UI, and documentation have been translated.
7. No secrets in the repo. New env variables are added to `.env.example`.
8. If anything in the spec is unclear or self-contradictory, **ask** instead of guessing.
9. If code already exists in the repo, adapt it to the spec rather than starting over, and explain what you're changing.

## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature>/` in this repo. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.
