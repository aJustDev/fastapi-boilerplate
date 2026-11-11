"""Figures for docs/deployment.md: python3 docs/img/deployment.py"""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
raiz = next(
    p for p in Path(__file__).resolve().parents if (p / ".claude/skills/esquemas-svg").is_dir()
)
sys.path.insert(0, str(raiz / ".claude/skills/esquemas-svg"))
from lienzo import AZUL, AZUL_F, BORDE, GRIS, TINTA, Lienzo, guardar  # noqa: E402


def caja(c, x, y, w, h, titulo, sub=None, color=GRIS):
    c.rect(x, y, w, h, fill="#fff", stroke=color, rx=6)
    n = c.parrafo(x + 12, y + 18, titulo, w - 24, size=12.5, bold=True, color=TINTA, lh=16)
    if sub:
        c.parrafo(x + 12, y + 18 + n * 15, sub, w - 24, size=11, color=GRIS, lh=14)


def cabecera(c, y, texto):
    c.rect(0, y, 760, 30, fill=AZUL_F, stroke=AZUL, rx=8)
    c.texto(380, y + 20, texto, size=13.5, color=AZUL, bold=True, anchor="middle")


def contenedores(c, y0):
    """Three app containers, one process each; returns the y of their middles."""
    middles = []
    for i, name in enumerate(("Container 1", "Container 2", "Container N")):
        y = y0 + 46 + i * 52
        caja(c, 16, y, 230, 44, name, "pool 5 + 10 and one LISTEN", color=AZUL)
        middles.append(y + 22)
    return middles


def postgres(c, cx, y, w=160):
    c.cilindro(cx, y, w, 78, AZUL, AZUL_F)
    c.texto(cx, y + 42, "PostgreSQL", size=12.5, bold=True, color=AZUL, anchor="middle")
    c.texto(cx, y + 60, "max_connections 100", size=11, color=GRIS, anchor="middle")


def topologies():
    c = Lienzo(760, 504, "dep-f1")

    # Self-hosted: the default
    c.rect(0, 0, 760, 230, fill="#fff", stroke=BORDE, rx=8)
    cabecera(c, 0, "Self-hosted: every app connection is a server connection")
    for i, y in enumerate(contenedores(c, 0)):
        c.flecha([(246, y), (536, 92 + (i - 1) * 14)], color=AZUL)
    c.texto(262, 84, "up to 16 each", size=11, bold=True, color=AZUL, halo="#fff")
    postgres(c, 620, 52)
    c.si(20, 208)
    c.texto(
        38,
        212,
        "containers x processes x (pool + overflow + 1) must stay under max_connections",
        size=12,
    )

    # Behind a pooler
    y0 = 246
    c.rect(0, y0, 760, 258, fill="#fff", stroke=BORDE, rx=8)
    cabecera(c, y0, "Behind a pooler in transaction mode")
    for y in contenedores(c, y0):
        c.flecha([(246, y), (300, y0 + 110)], color=AZUL)
    caja(c, 300, y0 + 76, 190, 66, "Pooler", "lends a server connection per transaction")
    c.flecha([(490, y0 + 100), (580, y0 + 100)], color=GRIS)
    c.texto(500, y0 + 92, "a few", size=11, bold=True, color=GRIS)
    postgres(c, 660, y0 + 64, w=150)
    c.flecha([(246, y0 + 186), (660, y0 + 186), (660, y0 + 146)], color=AZUL, dash="5 3")
    c.texto(300, y0 + 180, "DB_DIRECT_URL: LISTEN and migrations", size=11, bold=True, color=AZUL)
    for i, t in enumerate(
        (
            "DB_TRANSACTION_POOLER=true: no cached or named statements, timeouts per transaction",
            "The pooler's client limit now takes the sum of the pools (PgBouncer max_client_conn)",
        )
    ):
        c.si(20, y0 + 214 + i * 20)
        c.texto(38, y0 + 218 + i * 20, t, size=12)
    return c


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("deployment-connections", topologies),))
