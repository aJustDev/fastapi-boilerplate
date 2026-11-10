"""Ejemplo de esquemas con lienzo.py: python3 ejemplo.py [directorio] (por defecto, el actual).

Los tres patrones que mejor funcionan: antes y ahora, paso a paso y escenarios.
En un documento real va en <dir>/img/esquemas.py y escribe junto a si mismo.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
raiz = next(p for p in Path(__file__).resolve().parents if (p / ".claude/skills/esquemas-svg").is_dir())
sys.path.insert(0, str(raiz / ".claude/skills/esquemas-svg"))
from lienzo import *  # noqa: E402,F403


def caja(c, x, y, w, h, titulo, sub=None, color=GRIS, fondo="#fff", dash=None, size=12.5):
    """Caja con titulo en negrita y, debajo, texto pequeno partido en lineas."""
    c.rect(x, y, w, h, fill=fondo, stroke=color, rx=6, dash=dash)
    n = c.parrafo(x + 12, y + 20, titulo, w - 24, size=size, bold=True, color=color if color != GRIS else TINTA, lh=16)
    if sub:
        c.parrafo(x + 12, y + 20 + n * 16, sub, w - 24, size=11, color=GRIS, lh=14)


def cabecera(c, y, texto, color, fondo):
    c.rect(0, y, 760, 30, fill=fondo, stroke=color, rx=8)
    c.texto(380, y + 20, texto, size=13.5, color=color, bold=True, anchor="middle")


def antes_ahora():
    c = Lienzo(760, 518, "ej-f1")

    # ANTES
    c.rect(0, 0, 760, 222, fill="#fff", stroke=BORDE, rx=8)
    cabecera(c, 0, "ANTES · la exportación se hacía dentro de la petición", ROJO, ROJO_F)
    navegador(c, 12, 46, 170, 100, "Web")
    c.lineas(26, 96, ["El usuario pide", "la exportación"], size=12, lh=16)
    c.rect(300, 56, 180, 80, fill="#fff", stroke=GRIS, rx=8)
    c.servidor(312, 68, AZUL)
    c.texto(346, 80, "API", size=12.5, bold=True, color=AZUL)
    c.lineas(312, 108, ["genera el fichero", "mientras la web espera"], size=12, lh=16)
    c.flecha([(182, 86), (300, 86)], color=ROJO)
    c.texto(192, 78, "pide y espera", size=11, bold=True, color=ROJO)
    c.flecha([(300, 118), (182, 118)], color=ROJO, dash="5 3")
    c.lineas(192, 136, ["el fichero,", "o un corte"], size=11, lh=13, bold=True, color=ROJO)
    c.cilindro(640, 60, 150, 70, AZUL, AZUL_F)
    c.texto(640, 104, "Base de datos", size=12.5, bold=True, color=AZUL, anchor="middle")
    c.flecha([(480, 96), (565, 96)], color=GRIS)
    c.texto(490, 88, "consulta", size=11, color=GRIS)
    for i, t in enumerate(("Con muchos datos la petición pasaba de 60 s y el balanceador la cortaba: el usuario no recibía nada.",
                           "Si recargaba la página, empezaba otra exportación igual y la base de datos trabajaba el doble.")):
        c.no(24, 176 + i * 20)
        c.texto(38, 180 + i * 20, t, size=12)

    # AHORA
    y0 = 238
    c.rect(0, y0, 760, 280, fill="#fff", stroke=BORDE, rx=8)
    cabecera(c, y0, "AHORA · se encola un trabajo y la web pregunta cómo va", AZUL, AZUL_F)
    navegador(c, 12, y0 + 46, 170, 160, "Web")
    c.lineas(26, y0 + 96, ["Pide la exportación", "y sigue trabajando;", "pregunta cada 3 s"], size=12, lh=16)
    c.rect(300, y0 + 46, 180, 160, fill=AZUL_F, stroke=AZUL, rx=8)
    c.servidor(312, y0 + 58, AZUL)
    c.texto(346, y0 + 70, "API", size=12.5, bold=True, color=AZUL)
    c.lineas(312, y0 + 104, ["apunta el trabajo,", "responde al momento", "y entrega el fichero", "cuando está listo"], size=12, lh=16)
    pasos = (("1 · pide", AZUL, None, 1), ("2 · su número", AZUL, "5 3", -1),
             ("3 · ¿cómo va?", GRIS, "5 3", 1), ("4 · descarga", VERDE, None, -1))
    for i, (t, color, dash, sentido) in enumerate(pasos):
        y = y0 + 80 + i * 36
        c.flecha([(182, y), (300, y)][::sentido], color=color, dash=dash)
        c.texto(192, y - 6, t, size=11, bold=True, color=color)
    caja(c, 572, y0 + 46, 176, 64, "Trabajador", "genera el fichero aparte, sin prisa", color=AZUL)
    c.flecha([(480, y0 + 78), (572, y0 + 78)], color=AZUL)
    c.texto(490, y0 + 70, "cola", size=11, bold=True, color=AZUL)
    c.cilindro(660, y0 + 136, 150, 70, AZUL, AZUL_F)
    c.texto(660, y0 + 180, "Base de datos", size=12.5, bold=True, color=AZUL, anchor="middle")
    c.flecha([(660, y0 + 110), (660, y0 + 136)], color=GRIS)
    c.texto(668, y0 + 127, "consulta", size=11, color=GRIS, halo="#fff")
    for i, t in enumerate(("La petición dura menos de un segundo: el balanceador ya no la corta.",
                           "Si el usuario recarga, la web retoma el mismo trabajo en lugar de empezar otro.")):
        c.si(20, y0 + 234 + i * 20)
        c.texto(38, y0 + 238 + i * 20, t, size=12)
    return c


def paso_a_paso():
    c = Lienzo(760, 434, "ej-f2")
    X, W, XB, WB, H, PASO = 40, 320, 440, 320, 46, 66

    def principal(i, titulo, sub, color, fondo):
        y = i * PASO
        # las decisiones, en ambar y con forma de pastilla
        c.rect(X, y, W, H, fill=fondo, stroke=color, rx=8 if color != AMBAR else 22, sw=1.4)
        c.texto(X + W / 2, y + (19 if sub else 28), titulo, size=12.5, bold=True, color=color, anchor="middle")
        if sub:
            c.texto(X + W / 2, y + 36, sub, size=11, color=GRIS, anchor="middle")

    def rama(i, etiqueta, texto, color, fondo):
        y = i * PASO
        c.flecha([(X + W, y + H / 2), (XB, y + H / 2)], color=color, dash=None if etiqueta else "4 3")
        if etiqueta:
            c.texto((X + W + XB) / 2, y + H / 2 - 6, etiqueta, size=11, bold=True, color=color, anchor="middle")
        c.rect(XB, y, WB, H, fill=fondo, stroke=color, rx=6, sw=1.2)
        n = len(c.p)
        filas = c.parrafo(XB + 12, y + 19, texto, WB - 24, size=11.5, lh=14)
        if filas == 1:  # centrado vertical si cabe en una linea
            c.p[n] = c.p[n].replace(f'y="{y + 19}"', f'y="{y + 27}"')

    def baja(i, etiqueta=None):
        y = i * PASO + H
        c.flecha([(X + W / 2, y), (X + W / 2, y + PASO - H)], color=GRIS)
        if etiqueta:
            c.texto(X + W / 2 + 8, y + 14, etiqueta, size=11, bold=True, color=GRIS)

    principal(0, "1 · La web pide la exportación", "con los filtros que tiene la pantalla", AZUL, AZUL_F)
    baja(0)
    principal(1, "2 · ¿Tiene sesión y permiso?", None, AMBAR, AMBAR_F)
    rama(1, "no", "Rechazada: «No tienes permiso para exportar».", ROJO, ROJO_F)
    baja(1, "sí")
    principal(2, "3 · ¿Hay ya una igual en curso?", None, AMBAR, AMBAR_F)
    rama(2, "sí", "Se devuelve la que ya hay, sin empezar otra.", AZUL, AZUL_F)
    baja(2, "no")
    principal(3, "4 · Se encola el trabajo", "la API responde con su número", AZUL, AZUL_F)
    rama(3, None, "El trabajador la recoge en cuanto queda libre; como mucho dos a la vez.", GRIS, GRIS_F)
    baja(3)
    principal(4, "5 · ¿Termina en menos de 10 minutos?", None, AMBAR, AMBAR_F)
    rama(4, "no", "Se cancela y la web avisa: «La exportación ha tardado demasiado».", ROJO, ROJO_F)
    baja(4, "sí")
    principal(5, "6 · El fichero queda listo", "se puede descargar durante 24 h", VERDE, VERDE_F)

    y = 5 * PASO + H + 22
    c.rect(0, y, 760, 36, fill=GRIS_F, stroke=BORDE, rx=6, sw=1)
    c.parrafo(14, y + 23, "Pasadas las 24 h el fichero se borra solo. Si el usuario lo necesita otra vez, "
              "lanza otra exportación con los mismos filtros.", 732, size=12, lh=16)
    return c


def escenarios():
    c = Lienzo(760, 222, "ej-f3")
    XA, WA, XN, WN, H = 170, 272, 470, 290, 80
    c.texto(XA + WA / 2, 20, "Antes", size=12, bold=True, color=ROJO, anchor="middle")
    c.texto(XN + WN / 2, 20, "Ahora", size=12, bold=True, color=VERDE, anchor="middle")
    filas = (
        ("Recarga la página", "a mitad de una exportación",
         "Empieza otra exportación igual; la base de datos trabaja el doble y el usuario espera otra vez desde cero.",
         "La web recuerda el número del trabajo y sigue esperando el mismo."),
        ("Se reinicia el servidor", "por un despliegue",
         "La exportación se pierde sin aviso y el usuario solo ve un error de conexión.",
         "El trabajo sigue en la cola: otro trabajador lo retoma y la web no nota el corte."),
    )
    y = 34
    for titulo, sub, antes, ahora in filas:
        n = c.parrafo(0, y + 24, titulo, 150, size=13, bold=True, lh=17)
        c.parrafo(0, y + 24 + n * 17, sub, 150, size=11.5, color=GRIS, lh=15)
        c.rect(XA, y, WA, H, fill=ROJO_F, stroke=ROJO, rx=8)
        c.alerta(XA + 10, y + 10)
        c.parrafo(XA + 44, y + 26, antes, WA - 56, size=12, lh=15)
        c.flecha([(XA + WA + 4, y + H / 2), (XN - 4, y + H / 2)], color=VERDE, sw=2)
        c.rect(XN, y, WN, H, fill=VERDE_F, stroke=VERDE, rx=8)
        c.visto(XN + 10, y + 10)
        c.parrafo(XN + 44, y + 26, ahora, WN - 56, size=12, lh=15)
        y += H + 12
    return c


if __name__ == "__main__":
    salida = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    guardar(salida, (("antes-ahora", antes_ahora), ("paso-a-paso", paso_a_paso), ("escenarios", escenarios)))
