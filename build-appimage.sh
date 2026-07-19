#!/usr/bin/env bash
#
# Build a self-contained PDF Sherpa AppImage for Linux (x86_64).
#
# Bundles Python, Tcl/Tk, PyMuPDF and Pillow via PyInstaller, then packs the
# result with appimagetool.  The output lands in dist/ and needs no Python or
# system packages on the target machine -- just a glibc at least as new as the
# build host's.
#
# Usage:  ./build-appimage.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

ARCH="$(uname -m)"
VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' app.py | head -1)"
[[ -n "$VERSION" ]] || { echo "Could not read APP_VERSION from app.py" >&2; exit 1; }
echo "Building PDF Sherpa v$VERSION ($ARCH) AppImage ..."

BUILD="$HERE/build"
DIST="$HERE/dist"
VENV="$BUILD/venv"
APPDIR="$BUILD/AppDir"
TOOL="$BUILD/appimagetool-$ARCH.AppImage"
mkdir -p "$BUILD" "$DIST"

# 1. Build venv with the app deps + PyInstaller.
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --upgrade pip >/dev/null
fi
"$VENV/bin/python" -m pip install -r requirements.txt pyinstaller >/dev/null
echo "  deps ready"

# 2. Freeze the app (onedir -- faster startup, simpler to relocate).
rm -rf "$BUILD/pyi" "$DIST/PDFSherpa"
"$VENV/bin/pyinstaller" --noconfirm --clean --windowed \
    --name PDFSherpa \
    --distpath "$DIST" --workpath "$BUILD/pyi" --specpath "$BUILD/pyi" \
    --hidden-import PIL._tkinter_finder \
    --add-data "$HERE/HELP.md:." \
    --add-data "$HERE/sherpaicon.ico:." \
    --add-data "$HERE/sherpapdf.png:." \
    "$HERE/app.py" >/dev/null
echo "  PyInstaller bundle -> dist/PDFSherpa/"

# 3. Assemble the AppDir.
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" \
         "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a "$DIST/PDFSherpa/." "$APPDIR/usr/bin/"

# Square 256x256 icon (the source art is a wide banner) for the menu/AppImage.
"$VENV/bin/python" - "$HERE/sherpapdf.png" "$APPDIR/pdf-sherpa.png" <<'PY'
import sys
from PIL import Image
src, dst = sys.argv[1], sys.argv[2]
im = Image.open(src).convert("RGBA")
im.thumbnail((256, 256), Image.LANCZOS)
canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
canvas.paste(im, ((256 - im.width) // 2, (256 - im.height) // 2), im)
canvas.save(dst)
PY
cp "$APPDIR/pdf-sherpa.png" \
   "$APPDIR/usr/share/icons/hicolor/256x256/apps/pdf-sherpa.png"

cat > "$APPDIR/pdf-sherpa.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PDF Sherpa
Comment=Browse PDFs by topic
Exec=PDFSherpa %f
Icon=pdf-sherpa
Terminal=false
Categories=Office;Viewer;
MimeType=application/pdf;
EOF
cp "$APPDIR/pdf-sherpa.desktop" "$APPDIR/usr/share/applications/"

cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/PDFSherpa" "$@"
EOF
chmod +x "$APPDIR/AppRun"
echo "  AppDir assembled"

# 4. Fetch appimagetool + the static type2 runtime (both cached in build/).
if [[ ! -x "$TOOL" ]]; then
    echo "  downloading appimagetool ..."
    curl -fsSL -o "$TOOL" \
        "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-$ARCH.AppImage"
    chmod +x "$TOOL"
fi
# The statically-linked runtime uses fusermount3 and bundles libfuse, so the
# built AppImage runs on modern distros that ship only FUSE 3 (e.g. Ubuntu
# 22.04+) without needing the old libfuse2 package installed.
RUNTIME="$BUILD/runtime-$ARCH"
if [[ ! -x "$RUNTIME" ]]; then
    echo "  downloading AppImage runtime ..."
    curl -fsSL -o "$RUNTIME" \
        "https://github.com/AppImage/type2-runtime/releases/download/continuous/runtime-$ARCH"
    chmod +x "$RUNTIME"
fi

# 5. Pack it.  --appimage-extract-and-run avoids needing FUSE for the tool.
OUT="$DIST/PDFSherpa-$VERSION-$ARCH.AppImage"
rm -f "$OUT"
ARCH="$ARCH" "$TOOL" --appimage-extract-and-run --runtime-file "$RUNTIME" \
    "$APPDIR" "$OUT" >/dev/null
chmod +x "$OUT"

echo
echo "Done: $OUT"
ls -lh "$OUT"
