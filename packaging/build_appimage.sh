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

# AppRun: the AppImage entry point. Runs a glibc preflight check so
# users on too-old distros get a friendly error instead of cryptic
# "GLIBC_2.38 not found" link errors.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"

# Preflight: glibc minimum (set by build host's libc — 2.38 for Ubuntu 24.04)
NEED_GLIBC="2.38"
have_glibc="$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+' | tail -1)"
if [ -n "$have_glibc" ]; then
    # POSIX-shell version comparison via awk
    cmp=$(awk -v a="$have_glibc" -v b="$NEED_GLIBC" 'BEGIN {
        split(a, x, "."); split(b, y, ".");
        if (x[1]+0 < y[1]+0) print "lt";
        else if (x[1]+0 > y[1]+0) print "gt";
        else if (x[2]+0 < y[2]+0) print "lt";
        else print "ok";
    }')
    if [ "$cmp" = "lt" ]; then
        echo "OpenLimno Studio requires glibc >= $NEED_GLIBC; this system has $have_glibc." >&2
        echo "Compatible distros: Ubuntu 24.04+, Fedora 39+, Debian 13+, Arch, OpenSUSE Tumbleweed." >&2
        echo "On older distros, install the QGIS plugin instead (see README)." >&2
        exit 1
    fi
fi

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
