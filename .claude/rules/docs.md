---
name: docs
description: Every feature or structural piece has an explanatory doc in docs/, with diagrams drawn with the esquemas-svg skill.
paths:
    - app/**
    - docs/**
---

# Docs

- A new or changed feature or structural piece updates its doc in `docs/<topic>.md` in the same
  PR: what problem it solves, how it flows, what it guarantees and what it does not, how it is
  configured and extended. Written for someone who has not read the code. English.
- Diagrams with the `esquemas-svg` skill: flows, before/now and failure scenarios with
  `lienzo.py` (at most three per doc, each after a plain paragraph); simple maps of 4-7 boxes
  with Mermaid.
- One generator per doc in `docs/img/<topic>.py`, built on `docs/img/_figures.py` (`steps`,
  `scenarios`). Generate, then review every figure as PNG with
  `.claude/skills/esquemas-svg/png.sh` before accepting it; PNGs are not committed.
- A new doc goes in `docs/README.md`.

## Enforcement

CI regenerates every figure and fails if an SVG differs from its script. Whether a doc exists
and is up to date is checked in review.
