#!/usr/bin/env bash
#
# Build an AppImage from the PyInstaller dist/ directory.
#
# Prerequisites:
#   1. PyInstaller bundle already built:
#        pyinstaller --noconfirm packaging/openlimno-studio.spec
#   2. appimagetool downloaded (one-time):
#        wget -O ~/appimagetool 'https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage'
#        chmod +x ~/appimagetool
#
# Output: OpenLimnoStudio-x86_64.AppImage in repo root.

set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
DIST="$REPO/dist/openlimno-studio"
APPDIR="$REPO/build/AppDir"

if [ ! -d "$DIST" ]; then
    echo "ERROR: $DIST not found. Run pyinstaller first."
    exit 1
fi

echo "Building AppDir at $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -r "$DIST"/* "$APPDIR/usr/bin/"

# AppRun: the AppImage entry point
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
export PATH="$HERE/usr/bin:$PATH"
export LD_LIBRARY_PATH="$HERE/usr/bin/_internal:$LD_LIBRARY_PATH"
exec "$HERE/usr/bin/openlimno-studio" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Desktop entry — required by appimagetool
cat > "$APPDIR/openlimno-studio.desktop" <<'EOF'
[Desktop Entry]
Name=OpenLimno Studio
Comment=Open-source aquatic ecosystem modeling
Exec=openlimno-studio
Icon=openlimno-studio
Terminal=false
Type=Application
Categories=Science;Geography;
EOF

# Brand icon (256x256 PNG)
ICON_SRC="$REPO/packaging/icons/openlimno-studio.png"
if [ -f "$ICON_SRC" ]; then
    cp "$ICON_SRC" "$APPDIR/openlimno-studio.png"
else
    echo "ERROR: $ICON_SRC missing"
    exit 1
fi

# Build
APPIMAGETOOL="${APPIMAGETOOL:-$HOME/appimagetool}"
if [ ! -x "$APPIMAGETOOL" ]; then
    echo "ERROR: $APPIMAGETOOL not found or not executable."
    echo "Install with:"
    echo "  wget -O ~/appimagetool 'https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage'"
    echo "  chmod +x ~/appimagetool"
    exit 1
fi

cd "$REPO"
ARCH=x86_64 "$APPIMAGETOOL" "$APPDIR" OpenLimnoStudio-x86_64.AppImage
echo "✓ Built: $REPO/OpenLimnoStudio-x86_64.AppImage"
