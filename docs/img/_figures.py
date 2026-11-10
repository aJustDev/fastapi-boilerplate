"""Shared figure patterns for the docs, built on lienzo.py (skill esquemas-svg).

Each docs/img/<topic>.py describes its figures as data and calls these builders:
- steps: vertical flow of steps and decisions, with side branches;
- scenarios: rows of "situation | before | now".
"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
raiz = next(
    p for p in Path(__file__).resolve().parents if (p / ".claude/skills/esquemas-svg").is_dir()
)
sys.path.insert(0, str(raiz / ".claude/skills/esquemas-svg"))
from lienzo import (  # noqa: E402
    AMBAR,
    AMBAR_F,
    AZUL,
    AZUL_F,
    BORDE,
    GRIS,
    GRIS_F,
    ROJO,
    ROJO_F,
    VERDE,
    VERDE_F,
    Lienzo,
    guardar,
)

__all__ = ["guardar", "scenarios", "steps"]

# Layout of `steps`: main column at X (width W), branches at XB (width WB),
# boxes H high, one step every PASO px.
X, W, XB, WB, H, PASO = 40, 320, 440, 320, 46, 66
# Layout of `scenarios`: "before" column at XA (width WA), "now" column at XN (width WN).
XA, WA, XN, WN = 170, 272, 470, 290

# tone -> (stroke, fill)
TONES = {
    "step": (AZUL, AZUL_F),
    "decision": (AMBAR, AMBAR_F),
    "done": (VERDE, VERDE_F),
    "bad": (ROJO, ROJO_F),
    "note": (GRIS, GRIS_F),
}


def _lines(text, w, size, bold=False):
    """How many lines `parrafo` would use for `text` at width `w`."""
    return Lienzo(0, 0, "tmp").parrafo(0, 0, text, w, size=size, bold=bold)


def steps(cls, items, note=None):
    """Vertical flow on the left, branches on the right.

    items: dicts with
      title, sub (optional), tone ("step" | "decision" | "done"),
      branch (optional): (label or None, text, tone),
      down (optional): label of the arrow to the next step.
    """
    c = Lienzo(760, 0, cls)

    for i, it in enumerate(items):
        y = i * PASO
        color, fondo = TONES[it.get("tone", "step")]
        rx = 22 if it.get("tone") == "decision" else 8
        c.rect(X, y, W, H, fill=fondo, stroke=color, rx=rx, sw=1.4)
        sub = it.get("sub")
        c.texto(
            X + W / 2,
            y + (19 if sub else 28),
            it["title"],
            size=12.5,
            bold=True,
            color=color,
            anchor="middle",
        )
        if sub:
            c.texto(X + W / 2, y + 36, sub, size=11, color=GRIS, anchor="middle")

        if it.get("branch"):
            label, text, tone = it["branch"]
            bcolor, bfondo = TONES[tone]
            c.flecha(
                [(X + W, y + H / 2), (XB, y + H / 2)], color=bcolor, dash=None if label else "4 3"
            )
            if label:
                c.texto(
                    (X + W + XB) / 2,
                    y + H / 2 - 6,
                    label,
                    size=11,
                    bold=True,
                    color=bcolor,
                    anchor="middle",
                )
            c.rect(XB, y, WB, H, fill=bfondo, stroke=bcolor, rx=6, sw=1.2)
            filas = _lines(text, WB - 24, 11.5)
            c.parrafo(XB + 12, y + (27 if filas == 1 else 19), text, WB - 24, size=11.5, lh=14)

        if i < len(items) - 1:
            yb = y + H
            c.flecha([(X + W / 2, yb), (X + W / 2, yb + PASO - H)], color=GRIS)
            if it.get("down"):
                c.texto(X + W / 2 + 8, yb + 14, it["down"], size=11, bold=True, color=GRIS)

    c.h = (len(items) - 1) * PASO + H
    if note:
        y = c.h + 22
        h = 20 + _lines(note, 732, 12) * 16
        c.rect(0, y, 760, h, fill=GRIS_F, stroke=BORDE, rx=6, sw=1)
        c.parrafo(14, y + 23, note, 732, size=12, lh=16)
        c.h = y + h
    return c


def scenarios(cls, rows, before="Before", now="Now"):
    """rows: (title, sub, before_text, now_text)."""
    c = Lienzo(760, 0, cls)
    c.texto(XA + WA / 2, 20, before, size=12, bold=True, color=ROJO, anchor="middle")
    c.texto(XN + WN / 2, 20, now, size=12, bold=True, color=VERDE, anchor="middle")
    y = 34
    for title, sub, antes, ahora in rows:
        lines = max(_lines(antes, WA - 56, 12), _lines(ahora, WN - 56, 12))
        left = _lines(title, 150, 13, bold=True) * 17 + _lines(sub, 150, 11.5) * 15
        row_h = max(80, 26 + lines * 15, 18 + left)
        n = c.parrafo(0, y + 24, title, 150, size=13, bold=True, lh=17)
        c.parrafo(0, y + 24 + n * 17, sub, 150, size=11.5, color=GRIS, lh=15)
        c.rect(XA, y, WA, row_h, fill=ROJO_F, stroke=ROJO, rx=8)
        c.alerta(XA + 10, y + 10)
        c.parrafo(XA + 44, y + 26, antes, WA - 56, size=12, lh=15)
        c.flecha([(XA + WA + 4, y + row_h / 2), (XN - 4, y + row_h / 2)], color=VERDE, sw=2)
        c.rect(XN, y, WN, row_h, fill=VERDE_F, stroke=VERDE, rx=8)
        c.visto(XN + 10, y + 10)
        c.parrafo(XN + 44, y + 26, ahora, WN - 56, size=12, lh=15)
        y += row_h + 12
    c.h = y - 12
    return c
