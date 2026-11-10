"""Figures for docs/architecture.md: python3 docs/img/architecture.py"""

from pathlib import Path

from _figures import AZUL, AZUL_F, BORDE, GRIS, GRIS_F, ROJO, Lienzo, guardar, steps

X0, W = 150, 610  # where the bands start and their width
BAND_H, GAP = 54, 34


def request():
    return steps(
        "arch-f1",
        [
            {
                "title": "1 - Middleware",
                "sub": "proxy headers, trusted host, metrics, request id, CORS",
            },
            {
                "title": "2 - Router: app/<context>/api",
                "sub": "parses HTTP, resolves auth and repos via app.deps",
            },
            {
                "title": "3 - One use case per endpoint",
                "sub": "orders the steps, publishes events",
            },
            {
                "title": "4 - Service: the business rules",
                "sub": "reusable by several use cases",
                "branch": (
                    None,
                    "Plain CRUD has no service: the use case calls the repository.",
                    "note",
                ),
            },
            {"title": "5 - Repository", "sub": "queries through BaseRepo; flush, never commit"},
            {
                "title": "6 - get_session commits or rolls back",
                "sub": "before the response is sent",
                "tone": "done",
            },
        ],
        note="Contexts never import each other: they share data by id and react to each other "
        "through events. app.core is infrastructure and imports no context.",
    )


def _box(c, x, y, w, h, title, sub):
    c.rect(x, y, w, h, fill=AZUL_F, stroke=AZUL, rx=8, sw=1.4)
    c.texto(x + w / 2, y + 22, title, size=12.5, bold=True, color=AZUL, anchor="middle")
    c.texto(x + w / 2, y + 40, sub, size=11, color=GRIS, anchor="middle")


def _band_label(c, y, h, text):
    c.texto(0, y + h / 2 + 4, text, size=12, bold=True, color=GRIS)


def layers():
    c = Lienzo(760, 0, "arch-f2")

    # Composition
    y = 0
    _band_label(c, y, BAND_H, "Composition")
    _box(c, X0, y, 290, BAND_H, "app.api.v1", "composes the context routers")
    _box(c, X0 + 320, y, W - 320, BAND_H, "app.db_registry", "imports every model and handler")

    # Contexts, side by side, never importing each other
    y += BAND_H + GAP
    _band_label(c, y, BAND_H, "Contexts")
    _box(c, X0, y, 250, BAND_H, "app.auth", "users, roles, tokens")
    _box(c, X0 + W - 250, y, 250, BAND_H, "app.items", "example CRUD with events")
    mid = X0 + W / 2
    c.linea(X0 + 250, y + BAND_H / 2, X0 + W - 250, y + BAND_H / 2, color=ROJO, dash="4 3")
    c.no(mid, y + BAND_H / 2 - 12)
    c.texto(
        mid,
        y + BAND_H / 2 + 16,
        "no imports",
        size=11,
        bold=True,
        color=ROJO,
        anchor="middle",
        halo="#fff",
    )

    # Shared dependencies
    y += BAND_H + GAP
    _band_label(c, y, BAND_H, "Shared")
    _box(c, X0, y, W, BAND_H, "app.deps", "session, repositories, current user")

    # Infrastructure
    y += BAND_H + GAP
    _band_label(c, y, BAND_H, "Infrastructure")
    _box(c, X0, y, W, BAND_H, "app.core", "config, db, events, jobs, security, logging, metrics")

    # One axis for every band: imports only go down.
    c.flecha([(132, 6), (132, y + BAND_H - 6)], color=GRIS, sw=2)

    # Reading guide
    y += BAND_H + 22
    note = (
        "Imports go down: a band may import any band below it, never one above. "
        "The one exception is app.deps.auth, which reads the user from app.auth to give every "
        "context its current user."
    )
    c.rect(0, y, 760, 56, fill=GRIS_F, stroke=BORDE, rx=6, sw=1)
    c.parrafo(14, y + 23, note, 732, size=12, lh=16)
    c.h = y + 56
    return c


if __name__ == "__main__":
    guardar(
        Path(__file__).parent,
        (("architecture-request", request), ("architecture-layers", layers)),
    )
