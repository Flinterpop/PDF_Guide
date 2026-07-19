#!/usr/bin/env bash
#
# Add PDF Sherpa to your Linux application menu (a per-user .desktop entry).
# No root needed.  Re-run any time to refresh it.
#
#   ./install-linux.sh                      # menu entry that runs from source
#                                           #   (./run.sh + a local .venv)
#   ./install-linux.sh --appimage           # entry that runs the AppImage,
#                                           #   auto-found in dist/ or ~/Applications
#   ./install-linux.sh --appimage PATH      # ...or a specific .AppImage file
#   ./install-linux.sh --remove             # remove the menu entry + icon
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APPS_DIR="$DATA_DIR/applications"
ICONS_DIR="$DATA_DIR/icons/hicolor/256x256/apps"
DESKTOP="$APPS_DIR/pdf-sherpa.desktop"
ICON_DST="$ICONS_DIR/pdf-sherpa.png"
APPIMAGE_HOME="$HOME/Applications"          # permanent home for AppImage mode

refresh_caches() {
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APPS_DIR" >/dev/null 2>&1 || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
        gtk-update-icon-cache -f -t "$DATA_DIR/icons/hicolor" >/dev/null 2>&1 || true
}

# ---- parse arguments -------------------------------------------------------
MODE="source"
APPIMAGE_PATH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove)   MODE="remove" ;;
        --appimage) MODE="appimage"
                    if [[ -n "${2:-}" && "${2:0:1}" != "-" ]]; then
                        APPIMAGE_PATH="$2"; shift
                    fi ;;
        -h|--help)  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# ---- remove ----------------------------------------------------------------
if [[ "$MODE" == "remove" ]]; then
    rm -f "$DESKTOP" "$ICON_DST" \
          "$DATA_DIR/icons/pdf-sherpa.png"   # tidy up any older flat-icon install
    refresh_caches
    echo "Removed PDF Sherpa menu entry."
    echo "(Any AppImage under $APPIMAGE_HOME was left in place -- delete it by hand if you want.)"
    exit 0
fi

mkdir -p "$APPS_DIR" "$ICONS_DIR"

# Write a square 256x256 icon to $ICON_DST.  Prefer the one build-appimage.sh
# already made; otherwise square the wide source art with Pillow; otherwise
# just copy the source PNG as-is.
install_icon() {
    if [[ -f "$HERE/build/AppDir/pdf-sherpa.png" ]]; then
        cp -f "$HERE/build/AppDir/pdf-sherpa.png" "$ICON_DST"; return
    fi
    local py=""
    if [[ -x "$HERE/.venv/bin/python" ]] && \
       "$HERE/.venv/bin/python" -c 'import PIL' 2>/dev/null; then
        py="$HERE/.venv/bin/python"
    elif command -v python3 >/dev/null 2>&1 && python3 -c 'import PIL' 2>/dev/null; then
        py="python3"
    fi
    if [[ -n "$py" ]]; then
        "$py" - "$HERE/sherpapdf.png" "$ICON_DST" <<'PY'
import sys
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
im.thumbnail((256, 256), Image.LANCZOS)
canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
canvas.paste(im, ((256 - im.width) // 2, (256 - im.height) // 2), im)
canvas.save(dst)
PY
    else
        cp -f "$HERE/sherpapdf.png" "$ICON_DST"
    fi
}

# ---- pick the Exec line per mode -------------------------------------------
if [[ "$MODE" == "appimage" ]]; then
    # Locate the AppImage: explicit path, else newest in dist/, else ~/Applications.
    if [[ -z "$APPIMAGE_PATH" ]]; then
        APPIMAGE_PATH="$(ls -t "$HERE"/dist/PDFSherpa-*-*.AppImage \
                                "$APPIMAGE_HOME"/PDFSherpa-*.AppImage 2>/dev/null \
                         | head -1 || true)"
    fi
    if [[ -z "$APPIMAGE_PATH" || ! -f "$APPIMAGE_PATH" ]]; then
        echo "No AppImage found." >&2
        echo "Build one with ./build-appimage.sh, or download it from the releases" >&2
        echo "page, then re-run:  ./install-linux.sh --appimage /path/to/PDFSherpa-*.AppImage" >&2
        exit 1
    fi
    # Give it a permanent home + a version-independent symlink the launcher
    # points at, so dropping in a newer AppImage just needs the symlink moved.
    mkdir -p "$APPIMAGE_HOME"
    base="$(basename "$APPIMAGE_PATH")"
    if [[ "$(cd "$(dirname "$APPIMAGE_PATH")" && pwd)" != "$APPIMAGE_HOME" ]]; then
        cp -f "$APPIMAGE_PATH" "$APPIMAGE_HOME/$base"
    fi
    chmod +x "$APPIMAGE_HOME/$base"
    ln -sfn "$base" "$APPIMAGE_HOME/PDFSherpa.AppImage"
    EXEC="$APPIMAGE_HOME/PDFSherpa.AppImage %f"
    LAUNCH_NOTE="  AppImage: $APPIMAGE_HOME/$base"
else
    chmod +x "$HERE/run.sh"
    EXEC="$HERE/run.sh %f"
    LAUNCH_NOTE="  Runs from source via: $HERE/run.sh"
fi

install_icon

cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=PDF Sherpa
Comment=Browse PDFs by topic
Exec=$EXEC
Icon=pdf-sherpa
Terminal=false
Categories=Office;Viewer;
MimeType=application/pdf;
StartupWMClass=PDFSherpa
EOF
chmod +x "$DESKTOP"
refresh_caches

echo "Installed PDF Sherpa to your application menu ($MODE mode)."
echo "  Entry: $DESKTOP"
echo "$LAUNCH_NOTE"
echo "Launch it from your app launcher (you may need to log out/in to refresh the menu)."
