---
name: docs
description: Every feature or structural piece has a brief technical doc in docs/ describing what it is and how to use it, with diagrams from the esquemas-svg skill. No comparisons with previous versions.
paths:
    - app/**
    - docs/**
---

# Docs

- A new or changed feature or structural piece updates its doc in `docs/<topic>.md` in the same
  PR. English, brief and technical, for someone who has not read the code.
- Structure: one paragraph saying what the piece is and what it is for; **How it works**;
  **Usage**; **Configuration** (table); **Guarantees and limits**; **Files**. Drop the sections a
  piece does not need.
- Describe the piece as it is. Never compare with previous versions ("before/now", "used to",
  the bug that was fixed): that belongs in `CHANGELOG.md`, the PR or an ADR. If a sentence only
  makes sense to someone who knew the old code, remove it.
- Every claim matches the code: settings that exist and are used, real file paths, real
  defaults.
- Diagrams with the `esquemas-svg` skill: flows and component views of the current behavior with
  `lienzo.py` (at most three per doc, each after a paragraph); simple maps of 4-7 boxes with
  Mermaid (quote labels with `/` or brackets). One generator per doc in `docs/img/<topic>.py`
  on top of `docs/img/_figures.py`; review every figure as PNG with
  `.claude/skills/esquemas-svg/png.sh` before accepting it. PNGs are not committed.
- A new doc goes in `docs/README.md`.

## Enforcement

CI regenerates every figure and fails if an SVG differs from its script. Content is checked in
review.
