#!/usr/bin/env bash
# Installs Listo for the current user and adds it to your app menu.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/listo"
rm -rf "$DEST"
mkdir -p "$DEST" "$HOME/.local/share/applications"
cp -R "$SRC"/. "$DEST"/
sed "s|LISTO_DIR|$DEST|g" "$SRC/listo.desktop" > "$HOME/.local/share/applications/listo.desktop"
chmod +x "$DEST/Listo"
echo "Listo installed. Find it in your app menu, or run: $DEST/Listo"
