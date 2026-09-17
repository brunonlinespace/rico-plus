#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 /path/to/Rico_Plus-0.0.2-x86_64.AppImage" >&2
    exit 2
fi

IMAGE="$(readlink -f "$1")"
if [[ ! -f "$IMAGE" ]]; then
    echo "AppImage not found: $IMAGE" >&2
    exit 2
fi

chmod +x "$IMAGE"
echo "File information:"
file "$IMAGE"
echo
echo "Version check without requiring FUSE:"
"$IMAGE" --appimage-extract-and-run --version

echo
echo "Starting graphical smoke test. Close Rico Plus to finish."
"$IMAGE" --appimage-extract-and-run
