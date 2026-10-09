#!/usr/bin/env bash
# Wrap the PyInstaller folder into one double-clickable Linux file (an AppImage).
#
#   bash packaging/linux/build_appimage.sh dist/Listo out/Listo-linux-x64.AppImage
#
# People download the .AppImage, mark it executable once (right-click > Properties > "Allow
# executing" — most file managers ask automatically) and double-click. Nothing is installed.
set -euo pipefail

SRC=${1:?usage: build_appimage.sh <pyinstaller folder> <output .AppImage>}
OUT=${2:?usage: build_appimage.sh <pyinstaller folder> <output .AppImage>}
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
ARCH=x86_64
# Pinned release + checksum (CONTRIBUTING.md rule 10). To update: change both lines.
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
TOOL_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
APPDIR="$WORK/Listo.AppDir"
mkdir -p "$APPDIR/usr/lib" "$(dirname "$OUT")"

cp -a "$SRC" "$APPDIR/usr/lib/listo"
cp "$ROOT/listo/assets/icon.png" "$APPDIR/listo.png"
ln -s listo.png "$APPDIR/.DirIcon"

cat > "$APPDIR/AppRun" <<'SH'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/lib/listo/Listo" "$@"
SH
chmod +x "$APPDIR/AppRun"

sed -e 's|^Exec=.*|Exec=Listo %F|' -e 's|^Icon=.*|Icon=listo|' \
  "$ROOT/packaging/linux/listo.desktop" > "$APPDIR/listo.desktop"

curl -fsSL -o "$WORK/appimagetool" "$TOOL_URL"
echo "$TOOL_SHA256  $WORK/appimagetool" | sha256sum -c -
chmod +x "$WORK/appimagetool"
# --appimage-extract-and-run: works on CI machines without FUSE.
ARCH="$ARCH" "$WORK/appimagetool" --appimage-extract-and-run --no-appstream "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "built $OUT"
