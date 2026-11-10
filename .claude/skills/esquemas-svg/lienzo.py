"""Piezas para dibujar esquemas SVG explicativos (ver SKILL.md).

Sin markers ni ids: pandoc incrusta el SVG en el HTML y no reescribe las referencias url(#...).
Uso desde <dir>/img/esquemas.py:

    raiz = next(p for p in Path(__file__).resolve().parents if (p / ".claude/skills/esquemas-svg").is_dir())
    sys.path.insert(0, str(raiz / ".claude/skills/esquemas-svg"))
    from lienzo import *
"""
import math
from pathlib import Path
from xml.sax.saxutils import escape

AZUL, AZUL_F = "#1f4e79", "#e8f0f8"
VERDE, VERDE_F = "#2e7d32", "#e8f3e9"
ROJO, ROJO_F = "#b03a2e", "#fbeaea"
AMBAR, AMBAR_F = "#a35f00", "#fff3dc"
GRIS, GRIS_F, BORDE = "#6b7785", "#f2f5f9", "#c9d3df"
TINTA = "#222"


def ancho(texto, size, bold=False):
    """Ancho aproximado de un texto en Liberation Sans."""
    return len(texto) * size * (0.54 if bold else 0.48)


class Lienzo:
    def __init__(self, w, h, clase):
        self.w, self.h, self.c = w, h, clase
        self.p = []

    def rect(self, x, y, w, h, fill="#fff", stroke=GRIS, rx=6, dash=None, sw=1.2):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def texto(self, x, y, s, size=12, color=TINTA, bold=False, anchor="start", halo=None, italic=False):
        """s: texto o lista de (texto, {"bold":..., "color":..., "size":...}) en la misma linea."""
        partes = s if isinstance(s, list) else [(s, {})]
        spans = []
        for t, st in partes:
            a = []
            if st.get("bold", bold):
                a.append('font-weight="bold"')
            if st.get("italic", italic):
                a.append('font-style="italic"')
            a.append(f'fill="{st.get("color", color)}"')
            a.append(f'font-size="{st.get("size", size)}"')
            spans.append(f'<tspan {" ".join(a)}>{escape(t)}</tspan>')
        h = f' stroke="{halo}" stroke-width="4" stroke-linejoin="round" paint-order="stroke"' if halo else ""
        self.p.append(f'<text x="{x}" y="{y}" text-anchor="{anchor}"{h}>{"".join(spans)}</text>')

    def lineas(self, x, y, filas, size=12, lh=16, **kw):
        for i, f in enumerate(filas):
            self.texto(x, y + i * lh, f, size=size, **kw)

    def parrafo(self, x, y, texto, w, size=12, lh=None, bold=False, **kw):
        """Texto partido por palabras en lineas de como mucho w (ancho estimado); devuelve cuantas."""
        lh = lh or round(size * 1.33)
        filas, fila = [], ""
        for palabra in texto.split():
            prueba = f"{fila} {palabra}".strip()
            if fila and ancho(prueba, size, bold) > w:
                filas.append(fila)
                fila = palabra
            else:
                fila = prueba
        filas.append(fila)
        self.lineas(x, y, filas, size=size, lh=lh, bold=bold, **kw)
        return len(filas)

    def linea(self, x1, y1, x2, y2, color=GRIS, sw=1.2, dash=None):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.p.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{sw}"{d}/>')

    def punta(self, x, y, ang, color, t=8):
        a1, a2 = ang + math.radians(152), ang - math.radians(152)
        pts = f"{x},{y} {x + t * math.cos(a1):.1f},{y + t * math.sin(a1):.1f} {x + t * math.cos(a2):.1f},{y + t * math.sin(a2):.1f}"
        self.p.append(f'<polygon points="{pts}" fill="{color}"/>')

    def flecha(self, pts, color=AZUL, sw=1.6, dash=None):
        """Polilinea con punta en el ultimo punto."""
        d = f' stroke-dasharray="{dash}"' if dash else ""
        s = " ".join(f"{x},{y}" for x, y in pts)
        (xa, ya), (xb, yb) = pts[-2], pts[-1]
        ang = math.atan2(yb - ya, xb - xa)
        # la linea acaba antes de la punta para que no asome por ella
        pts2 = pts[:-1] + [(xb - 6 * math.cos(ang), yb - 6 * math.sin(ang))]
        s = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts2)
        self.p.append(f'<polyline points="{s}" fill="none" stroke="{color}" stroke-width="{sw}"{d}/>')
        self.punta(xb, yb, ang, color)

    def llave(self, x, y, color):
        """Llave de 22x10 con el ojo en (x+5, y+5)."""
        self.p.append(
            f'<g fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round">'
            f'<circle cx="{x + 5}" cy="{y + 5}" r="4"/>'
            f'<path d="M{x + 9} {y + 5} H{x + 22} M{x + 17} {y + 5} V{y + 9} M{x + 21} {y + 5} V{y + 8}"/></g>')

    def ficha(self, x, y, w, etiqueta, color, fondo, h=26, size=12):
        """Credencial: caja redondeada con llave y texto; w=None, ancho segun el texto."""
        w = w or round(37 + len(etiqueta) * size * 0.6 + 8)
        self.rect(x, y, w, h, fill=fondo, stroke=color, rx=h / 2, sw=1.4)
        self.llave(x + 9, y + h / 2 - 5, color)
        self.texto(x + 37, y + h / 2 + size * 0.36, etiqueta, size=size, color=color, bold=True)

    def script(self, x, y, w, h=28):
        self.rect(x, y, w, h, fill="#eef0f3", stroke=GRIS, rx=h / 2)
        self.texto(x + 12, y + h / 2 + 4.5, [("</>", {"bold": True, "color": GRIS}), ("  Script de la página", {})], size=12)

    def si(self, x, y, color=VERDE):
        self.p.append(f'<path d="M{x} {y - 4} l3.5 4 l6.5 -8" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')

    def no(self, x, y, color=ROJO, t=4.5):
        self.p.append(f'<path d="M{x - t} {y - t} L{x + t} {y + t} M{x + t} {y - t} L{x - t} {y + t}" stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>')

    def alerta(self, x, y, color=ROJO):
        """Triangulo de aviso de 24x22."""
        self.p.append(f'<path d="M{x + 12} {y} L{x + 24} {y + 21} H{x} Z" fill="{color}" stroke="{color}" stroke-width="2" stroke-linejoin="round"/>')
        self.p.append(f'<path d="M{x + 12} {y + 7} V{y + 14} M{x + 12} {y + 17.5} V{y + 18}" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>')

    def visto(self, x, y, color=VERDE):
        """Circulo con marca de 24x24."""
        self.p.append(f'<circle cx="{x + 12}" cy="{y + 12}" r="12" fill="{color}"/>')
        self.p.append(f'<path d="M{x + 6.5} {y + 12.5} l3.8 4 l7.5 -8.5" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')

    def persona(self, x, y, color):
        self.p.append(f'<g fill="{color}"><circle cx="{x + 11}" cy="{y + 7}" r="6"/>'
                      f'<path d="M{x} {y + 28} a11 11 0 0 1 22 0 z"/></g>')

    def servidor(self, x, y, color):
        for i in range(3):
            self.rect(x, y + i * 9, 24, 7, fill=color, stroke=color, rx=1.5, sw=1)
            self.p.append(f'<circle cx="{x + 19}" cy="{y + i * 9 + 3.5}" r="1.4" fill="#fff"/>')

    def candado(self, x, y, color):
        self.p.append(f'<path d="M{x + 6} {y + 11} v-4 a6 6 0 0 1 12 0 v4" fill="none" stroke="{color}" stroke-width="2.4"/>')
        self.rect(x + 2, y + 11, 20, 15, fill=color, stroke=color, rx=2.5, sw=1)

    def movil(self, x, y, color):
        self.rect(x + 4, y, 16, 28, fill="#fff", stroke=color, rx=3, sw=2)
        self.linea(x + 9, y + 24, x + 15, y + 24, color=color, sw=2)

    def cilindro(self, cx, y, w, h, color, fondo):
        rx, ry = w / 2, 6
        self.p.append(
            f'<path d="M{cx - rx} {y + ry} v{h - 2 * ry} a{rx} {ry} 0 0 0 {w} 0 v{-(h - 2 * ry)}" fill="{fondo}" stroke="{color}" stroke-width="1.4"/>'
            f'<ellipse cx="{cx}" cy="{y + ry}" rx="{rx}" ry="{ry}" fill="{fondo}" stroke="{color}" stroke-width="1.4"/>')

    def svg(self):
        m = 3  # margen: los bordes en x=0 o x=w no se recortan
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-m} {-m} {self.w + 2 * m} {self.h + 2 * m}" '
                f'width="{self.w + 2 * m}" height="{self.h + 2 * m}" '
                f'font-family="Liberation Sans, DejaVu Sans, Arial, sans-serif">\n<g class="{self.c}">\n'
                + "\n".join(self.p) + "\n</g>\n</svg>\n")


def navegador(c, x, y, w, h, etiqueta=""):
    """Ventana de navegador con barra y etiqueta."""
    c.rect(x, y, w, h, fill="#fff", stroke=GRIS, rx=8)
    c.p.append(f'<path d="M{x} {y + 24} V{y + 8} a8 8 0 0 1 8 -8 H{x + w - 8} a8 8 0 0 1 8 8 V{y + 24} Z" fill="#e6eaf0" stroke="{GRIS}" stroke-width="1.2"/>')
    for i, col in enumerate(("#e06c5f", "#e8b04b", "#6cbf6c")):
        c.p.append(f'<circle cx="{x + 14 + i * 12}" cy="{y + 12}" r="4" fill="{col}"/>')
    c.texto(x + 54, y + 16, etiqueta, size=11, color=GRIS)


def guardar(directorio, figuras):
    """figuras: (nombre, funcion que devuelve un Lienzo); escribe <directorio>/<nombre>.svg."""
    for nombre, f in figuras:
        ruta = Path(directorio) / f"{nombre}.svg"
        ruta.write_text(f().svg(), encoding="utf-8")
        print(ruta)
