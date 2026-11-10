# Architecture decision records

An ADR records one decision that shapes the code: what was decided, why, what else was
considered and what it costs. It is written when the decision is made and is not rewritten
afterwards; a later decision that changes it gets its own ADR and marks the old one as
superseded.

Write one when a change introduces a cross-cutting pattern, a new dependency of the stack, or a
rule that other code must follow. Copy [000-template.md](000-template.md) to `NNN-<slug>.md`
with the next number.

| ADR | Title | Status |
|---|---|---|
| [001](001-stack.md) | Base stack | accepted |
| [002](002-alembic.md) | Schema migrations with Alembic | accepted |
