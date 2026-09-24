#!/usr/bin/env bash
# Reproducible build: fetch the STOCK proprietary driver from Canonical's OEM
# repo and apply the CV2 patches locally. This avoids relying on the prebuilt
# binary in this repo (and is the recommended path for a clean GitHub fork).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
UPSTREAM="https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom"
UPSTREAM_COMMIT="f7d31fcb9f6952d7d76ba50287e000c29760589d"

echo "[*] Fetching tested upstream revision $UPSTREAM_COMMIT ..."
git init -q "$WORK/up"
git -C "$WORK/up" remote add origin "$UPSTREAM"
git -C "$WORK/up" fetch -q --depth 1 origin "$UPSTREAM_COMMIT"
git -C "$WORK/up" checkout -q --detach FETCH_HEAD

STOCK="$WORK/up/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
[[ -f "$STOCK" ]] || { echo "stock .so not found in upstream tree" >&2; exit 1; }

echo "[*] Verifying stock and patched SHA-256 and applying CV2 patches ..."
mkdir -p "$HERE/prebuilt"
python3 "$HERE/patch_driver.py" "$STOCK" "$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

echo "[*] Copying firmware blobs from upstream ..."
mkdir -p "$HERE/firmware"
cp -- "$WORK"/up/var/lib/fprint/fw/* "$HERE/firmware/"

echo "[*] Done. Now run:  ./install.sh"
