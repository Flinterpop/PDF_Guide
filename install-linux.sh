#!/usr/bin/env bash
#
# Add PDF Sherpa to your Linux application menu (a per-user .desktop entry that
# runs ./run.sh).  No root needed.  Re-run any time to refresh it.
#
#     ./install-linux.sh            # install / update the menu entry
#     ./install-linux.sh --remove   # remove it
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons"
DESKTOP="$APPS_DIR/pdf-sherpa.desktop"
ICON_SRC="$HERE/sherpapdf.png"
ICON_DST="$ICONS_DIR/pdf-sherpa.png"

if [[ "${1:-}" == "--remove" ]]; then
    rm -f "$DESKTOP" "$ICON_DST"
    command -v update-desktop-database >/dev/null && \
        update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
    echo "Removed PDF Sherpa menu entry."
    exit 0
fi

mkdir -p "$APPS_DIR" "$ICONS_DIR"
[[ -f "$ICON_SRC" ]] && cp -f "$ICON_SRC" "$ICON_DST"
chmod +x "$HERE/run.sh"

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=PDF Sherpa
Comment=Browse PDFs by topic
Exec=$HERE/run.sh %f
Icon=$ICON_DST
Terminal=false
Categories=Office;Viewer;
MimeType=application/pdf;
EOF

chmod +x "$DESKTOP"
command -v update-desktop-database >/dev/null && \
    update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true

echo "Installed PDF Sherpa to your application menu."
echo "  Entry: $DESKTOP"
echo "Launch it from your app launcher, or run ./run.sh directly."
