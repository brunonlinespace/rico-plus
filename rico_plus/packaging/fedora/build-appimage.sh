#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROGRAM_ROOT="$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)"
PROJECT_ROOT="$(CDPATH= cd -- "$PROGRAM_ROOT/.." && pwd)"
APP_NAME="Rico Plus"
APP_ID="rico-plus"
APP_VERSION="0.0.2"
PUBLISHER_ID="brunonlinespace"
DESKTOP_ID="io.github.brunonlinespace.rico_plus"
ARCH="${ARCH:-x86_64}"

SOURCE_ENTRY="$PROJECT_ROOT/main.py"
PROJECT_MANIFEST="$PROGRAM_ROOT/rico-plus.json"
SOURCE_MANIFEST="$PROGRAM_ROOT/SOURCE_MANIFEST.sha256"

# Installing system dependencies requires sudo; building the application does
# not. Running the build as root creates root-owned build products and can make
# later normal-user rebuilds fail. Controlled root-based containers may opt in.
if [[ "${EUID:-$(id -u)}" -eq 0 && "${ALLOW_ROOT_BUILD:-0}" != "1" ]]; then
    cat >&2 <<'EOF'
Do not run build-appimage.sh with sudo.

Run the dependency helper normally (it invokes sudo only for dnf):
    ./rico_plus/packaging/fedora/install-build-deps.sh

Then build as your regular user:
    ./rico_plus/packaging/fedora/build-appimage.sh

For a controlled root-based CI/container only:
    ALLOW_ROOT_BUILD=1 ./rico_plus/packaging/fedora/build-appimage.sh
EOF
    exit 2
fi

FEDORA_RELEASE="unknown"
if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    echo "Build host: ${PRETTY_NAME:-unknown Linux}"
    if [[ "${ID:-}" == "fedora" ]]; then
        FEDORA_RELEASE="${VERSION_ID:-unknown}"
        case "$FEDORA_RELEASE" in
            43|44)
                echo "Fedora $FEDORA_RELEASE build host recognized."
                ;;
            *)
                echo "Warning: validated for Fedora 43 and 44; detected ${PRETTY_NAME:-unknown}." >&2
                ;;
        esac
    else
        echo "Warning: this helper is intended for Fedora; detected ${PRETTY_NAME:-unknown}." >&2
    fi
fi

if [[ "$ARCH" != "x86_64" ]]; then
    echo "The public AppImage build currently supports ARCH=x86_64 only." >&2
    exit 2
fi

BUILD_ROOT="${BUILD_ROOT:-$PROGRAM_ROOT/build/appimage-fedora${FEDORA_RELEASE}-$ARCH}"
VENV="$BUILD_ROOT/venv"
DIST_ROOT="$BUILD_ROOT/dist"
WORK_ROOT="$BUILD_ROOT/work"
APPDIR="$BUILD_ROOT/RicoPlus.AppDir"
OUTPUT_DIR="${OUTPUT_DIR:-$PROGRAM_ROOT/dist}"
OUTPUT="$OUTPUT_DIR/Rico_Plus-${APP_VERSION}-${ARCH}.AppImage"
TOOL_DIR="$BUILD_ROOT/tools"
APPIMAGETOOL="$TOOL_DIR/appimagetool-$ARCH.AppImage"
APPIMAGETOOL_URL="${APPIMAGETOOL_URL:-https://github.com/AppImage/appimagetool/releases/latest/download/appimagetool-${ARCH}.AppImage}"

# Suite/package identity and provenance inputs are mandatory.
for required_input in "$SOURCE_ENTRY" "$PROJECT_MANIFEST" "$SOURCE_MANIFEST"; do
    if [[ ! -f "$required_input" ]]; then
        echo "Missing required source identity/provenance input: $required_input" >&2
        exit 3
    fi
done

python3 - "$PROJECT_MANIFEST" "$APP_NAME" "$APP_ID" "$APP_VERSION" "$PUBLISHER_ID" "$DESKTOP_ID" <<'PYIDENT'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
name, app_id, version, publisher, desktop_id = sys.argv[2:]
data = json.loads(path.read_text(encoding="utf-8"))
assert data.get("name") == name, "application name mismatch"
assert data.get("id") == app_id, "application ID mismatch"
assert data.get("version") == version, "application version mismatch"
assert data.get("publisher_id") == publisher, "publisher ID mismatch"
assert data.get("desktop_id") == desktop_id, "desktop ID mismatch"
PYIDENT

# Validate only release-relevant source before creating generated build files.
# Local __pycache__ and .pyc files are harmless ignored artifacts; the checker
# rejects them only if Git reports that they are tracked.
echo "Running source release checks..."
PYTHONDONTWRITEBYTECODE=1 python3 "$PROGRAM_ROOT/tools/release_check.py"

echo "Cleaning build directory: $BUILD_ROOT"
rm -rf "$BUILD_ROOT"
mkdir -p "$BUILD_ROOT" "$DIST_ROOT" "$WORK_ROOT" "$APPDIR" "$OUTPUT_DIR" "$TOOL_DIR"

python3 -m venv "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip wheel setuptools
python -m pip install \
    -r "$PROGRAM_ROOT/requirements.txt" \
    -r "$SCRIPT_DIR/requirements-build.txt"

echo "Build toolchain:"
python --version
python -c 'import PyQt6.QtCore as q; print(f"PyQt6/Qt: {q.PYQT_VERSION_STR}/{q.QT_VERSION_STR}")'
python -m PyInstaller --version

python -m PyInstaller \
    --clean \
    --noconfirm \
    --distpath "$DIST_ROOT" \
    --workpath "$WORK_ROOT" \
    "$PROGRAM_ROOT/packaging/pyinstaller/rico-plus.spec"

BUNDLE="$DIST_ROOT/rico-plus"
if [[ ! -x "$BUNDLE/rico-plus" ]]; then
    echo "PyInstaller executable was not created: $BUNDLE/rico-plus" >&2
    exit 3
fi

mkdir -p \
    "$APPDIR/usr/bin" \
    "$APPDIR/usr/lib/rico-plus" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/16x16/apps" \
    "$APPDIR/usr/share/icons/hicolor/32x32/apps" \
    "$APPDIR/usr/share/icons/hicolor/48x48/apps" \
    "$APPDIR/usr/share/icons/hicolor/64x64/apps" \
    "$APPDIR/usr/share/icons/hicolor/128x128/apps" \
    "$APPDIR/usr/share/icons/hicolor/256x256/apps" \
    "$APPDIR/usr/share/icons/hicolor/512x512/apps" \
    "$APPDIR/usr/share/metainfo" \
    "$APPDIR/usr/share/doc/rico-plus"

cp -a "$BUNDLE/." "$APPDIR/usr/lib/rico-plus/"
ln -s ../lib/rico-plus/rico-plus "$APPDIR/usr/bin/rico-plus"

install -m 0755 "$PROGRAM_ROOT/packaging/appimage/AppRun" "$APPDIR/AppRun"
install -m 0644 \
    "$PROGRAM_ROOT/packaging/appimage/rico-plus.desktop" \
    "$APPDIR/rico-plus.desktop"
install -m 0644 \
    "$PROGRAM_ROOT/packaging/appimage/rico-plus.desktop" \
    "$APPDIR/usr/share/applications/rico-plus.desktop"
install -m 0644 \
    "$PROGRAM_ROOT/packaging/appimage/io.github.brunonlinespace.rico_plus.metainfo.xml" \
    "$APPDIR/usr/share/metainfo/io.github.brunonlinespace.rico_plus.metainfo.xml"

for icon_size in 16 32 48 64 128 256 512; do
    install -m 0644 \
        "$PROGRAM_ROOT/assets/icons/ricopad-${icon_size}.png" \
        "$APPDIR/usr/share/icons/hicolor/${icon_size}x${icon_size}/apps/rico-plus.png"
done
install -m 0644 \
    "$PROGRAM_ROOT/assets/icons/ricopad.png" \
    "$APPDIR/rico-plus.png"
ln -s rico-plus.png "$APPDIR/.DirIcon"

install -m 0644 "$PROGRAM_ROOT/LICENSE" "$APPDIR/usr/share/doc/rico-plus/LICENSE"
install -m 0644 "$PROGRAM_ROOT/docs/README.md" "$APPDIR/usr/share/doc/rico-plus/README.md"
install -m 0644 "$PROGRAM_ROOT/docs/RELEASE_NOTES.md" "$APPDIR/usr/share/doc/rico-plus/RELEASE_NOTES.md"

if command -v desktop-file-validate >/dev/null 2>&1; then
    desktop-file-validate "$APPDIR/rico-plus.desktop"
fi
if command -v appstreamcli >/dev/null 2>&1; then
    appstreamcli validate --no-net \
        "$APPDIR/usr/share/metainfo/io.github.brunonlinespace.rico_plus.metainfo.xml"
fi

# Test the unfused AppDir before producing the compressed image.
"$APPDIR/AppRun" --version

curl --fail --location --retry 3 \
    "$APPIMAGETOOL_URL" \
    --output "$APPIMAGETOOL"
chmod +x "$APPIMAGETOOL"

rm -f "$OUTPUT"
export ARCH

# Prefer direct execution, but use appimagetool's extraction path on hosts
# where its embedded AppImage cannot be mounted through FUSE.
if "$APPIMAGETOOL" --version >/dev/null 2>&1; then
    "$APPIMAGETOOL" "$APPDIR" "$OUTPUT"
else
    "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" "$OUTPUT"
fi

chmod +x "$OUTPUT"
"$OUTPUT" --appimage-extract-and-run --version

sha256sum "$OUTPUT" > "$OUTPUT.sha256"

cat > "$OUTPUT.build-info.txt" <<EOF
Rico Plus version: $APP_VERSION
Architecture: $ARCH
Build host: ${PRETTY_NAME:-unknown Linux}
Fedora release: $FEDORA_RELEASE
Python: $(python --version 2>&1)
PyInstaller: $(python -m PyInstaller --version)
PyQt6/Qt: $(python -c 'import PyQt6.QtCore as q; print(f"{q.PYQT_VERSION_STR}/{q.QT_VERSION_STR}")')
main.py SHA-256: $(sha256sum "$SOURCE_ENTRY" | awk '{print $1}')
SOURCE_MANIFEST.sha256 SHA-256: $(sha256sum "$SOURCE_MANIFEST" | awk '{print $1}')
Project manifest SHA-256: $(sha256sum "$PROJECT_MANIFEST" | awk '{print $1}')
Runtime requirements SHA-256: $(sha256sum "$PROGRAM_ROOT/requirements.txt" | awk '{print $1}')
Builder SHA-256: $(sha256sum "$0" | awk '{print $1}')
Output SHA-256: $(sha256sum "$OUTPUT" | awk '{print $1}')
EOF

echo
echo "AppImage created successfully:"
echo "  $OUTPUT"
echo "Checksum:"
cat "$OUTPUT.sha256"
echo "Build information:"
echo "  $OUTPUT.build-info.txt"
