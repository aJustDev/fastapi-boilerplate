#!/bin/sh
# Uso: png.sh fichero.svg [...]: deja fichero.png al lado, a escala 2, para revisar el esquema.
# Navegador: $CHROME, google-chrome, chromium o el Chromium de Playwright, por ese orden.
set -e
chrome=${CHROME:-$(command -v google-chrome || command -v chromium || command -v chromium-browser ||
  ls -d "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | sort -V | tail -1 || true)}
[ -n "$chrome" ] || { echo "Sin Chrome ni Chromium: CHROME=/ruta/al/navegador png.sh ..." >&2; exit 1; }
for f in "$@"; do
  w=$(sed -n 's/.*<svg[^>]* width="\([0-9]*\).*/\1/p' "$f" | head -1)
  h=$(sed -n 's/.*<svg[^>]* height="\([0-9]*\).*/\1/p' "$f" | head -1)
  "$chrome" --headless=new --disable-gpu --hide-scrollbars \
    --force-device-scale-factor=2 --window-size="$w,$h" \
    --screenshot="${f%.svg}.png" "file://$(realpath "$f")" 2>/dev/null
  echo "${f%.svg}.png"
done
