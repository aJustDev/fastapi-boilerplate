---
name: esquemas-svg
description: Dibuja esquemas SVG explicativos (antes y ahora, paso a paso, escenarios de fallo o ataque) con lienzo.py, para informes, documentos o README que lee alguien que tiene que entender como funciona algo sin leer el codigo. Usar cuando se pida un esquema, diagrama o dibujo elaborado para un documento, o cuando un informe para un jefe o cliente explique un flujo o un cambio de seguridad.
---

# Esquemas SVG con lienzo.py

`lienzo.py` (en este directorio) dibuja SVG pieza a pieza, solo con la libreria estandar de Python. `ejemplo.py` tiene los tres patrones que mejor funcionan; partir siempre de el.

Esta skill puede estar en `.claude/skills/esquemas-svg/` del proyecto o de `~`; abajo, `<skill>` es ese directorio.

## Cuando

- Cuando el lector tiene que entender como funciona algo: que cambia (antes y ahora), que pasa en cada paso, o que pasa ante un fallo o un ataque.
- Como mucho tres por documento, y cada uno con un parrafo antes que explique la idea en llano.
- Para un mapa simple de que piezas se tocan (4-7 cajas) basta un Mermaid, si el documento lo admite.

## Como

1. Crear `<dir>/img/esquemas.py` copiando la estructura de `ejemplo.py`:
   - importacion: las dos lineas de `ejemplo.py` que buscan `.claude/skills/esquemas-svg` subiendo desde el fichero (valen para la skill del proyecto y para la de `~`) y `from lienzo import *`;
   - una funcion por figura que devuelve un `Lienzo`;
   - al final, `guardar(Path(__file__).parent, (("nombre", funcion), ...))`.
2. Generar: `python3 <dir>/img/esquemas.py`.
3. Revisar siempre en PNG antes de darlo por bueno: `<skill>/png.sh <dir>/img/*.svg` y mirar cada PNG con Read. Buscar textos que se salen de su caja, solapes, flechas que cruzan textos y bordes cortados. Corregir y repetir. Borrar los PNG al acabar si el documento no los usa.
4. Enlazar:
   - en Markdown: `![Pie](img/nombre.svg)`;
   - con pandoc a HTML o PDF: `![Pie](img/nombre.svg){.esquema}` y en el CSS `figure svg.esquema { width: 100%; height: auto; }`.

## Piezas

Coordenadas en px con el origen arriba a la izquierda; la `y` de un texto es su linea base.

- `Lienzo(w, h, clase)`: ancho 760, que es el de una pagina A4. `clase`, distinta en cada figura (`xx-f1`, `xx-f2`).
- `rect(x, y, w, h, fill, stroke, rx, dash, sw)`, `linea(...)`.
- `texto(x, y, s, size, color, bold, anchor, halo, italic)`. `s` puede ser una lista de `(texto, {"bold", "color", "size"})` en la misma linea. `halo="#fff"` cuando el texto pisa una linea.
- `lineas(x, y, filas, ...)` y `parrafo(x, y, texto, w, ...)`: este parte el texto al ancho `w` y devuelve cuantas lineas ocupa.
- `flecha(pts, color, sw, dash)`: polilinea con punta en el ultimo punto.
- Marcas: `si`, `no`, `alerta`, `visto`.
- Iconos: `persona`, `servidor`, `movil`, `candado`, `llave`, `cilindro` (base de datos, con `cx` del centro), `ficha` (credencial con llave), `script` y `navegador(c, ...)` (funcion, no metodo).
- Colores: `AZUL`, `VERDE`, `ROJO`, `AMBAR`, `GRIS`, cada uno con su fondo `_F`. Ademas, `BORDE` y `TINTA`.

## Reglas de diseno

- **Colores con significado, siempre los mismos:**
  - rojo: antes, problema o ataque;
  - verde: ahora, o lo que sale bien;
  - azul: nuestro sistema y el camino normal;
  - ambar: decisiones (pastilla con `rx=22`);
  - gris: neutro y notas.
- **Tamanos:** titulo de panel 13.5 en negrita, titulo de caja 12.5 en negrita, texto 12, etiquetas de flecha 11 en negrita y del color de la flecha (encima, a `y - 6`).
- **Textos:** frases cortas y funcionales, con tildes y enes, sin nombres de ficheros ni variables salvo que el lector sea tecnico.
- **Ancho de los textos:** `ancho()` es una estimacion para Liberation Sans. Hay que dejar holgura y fiarse del PNG.
- **Sin markers, ids ni `url(#...)`, ni degradados o filtros con id:** pandoc mete el SVG dentro del HTML y no reescribe esas referencias. Las puntas de flecha ya las dibuja `flecha()`.
- **Patrones de `ejemplo.py`:**
  - `antes_ahora`: dos paneles con cabecera y notas con `no` y `si` debajo;
  - `paso_a_paso`: columna de pasos con ramas a la derecha (`principal`, `rama`, `baja`);
  - `escenarios`: filas con la situacion a la izquierda y celdas de antes y ahora.

## Requisitos

- Python 3.
- Fuente Liberation Sans (paquete `fonts-liberation`). Sin ella el navegador usa otra fuente y los textos pueden salirse de las cajas.
- Chrome o Chromium para `png.sh`: busca `google-chrome`, `chromium` y el Chromium de Playwright (`~/.cache/ms-playwright`). Otro navegador: `CHROME=/ruta png.sh ...`.
