#!/usr/bin/env bash
# Reproducible build: fetch the STOCK proprietary driver from Canonical's OEM
# repo and apply the CV2 patches locally. This avoids relying on the prebuilt
# binary in this repo (and is the recommended path for a clean GitHub fork).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(mktemp -d)"
UPSTREAM="https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom"
UPSTREAM_COMMIT="f7d31fcb9f6952d7d76ba50287e000c29760589d"
STOCK_SHA256="54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172"
PATCHED_SHA256="308055122a9d4b7b723325a4935f25a23300ac656962c9db7e5285164233c5ab"
trap 'rm -rf "$WORK"' EXIT

echo "[*] Fetching tested upstream revision $UPSTREAM_COMMIT ..."
git init -q "$WORK/up"
git -C "$WORK/up" remote add origin "$UPSTREAM"
git -C "$WORK/up" fetch -q --depth 1 origin "$UPSTREAM_COMMIT"
git -C "$WORK/up" checkout -q --detach FETCH_HEAD

STOCK="$WORK/up/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
[[ -f "$STOCK" ]] || { echo "stock .so not found in upstream tree" >&2; exit 1; }

ACTUAL_SHA256="$(sha256sum "$STOCK" | cut -d' ' -f1)"
if [[ "$ACTUAL_SHA256" != "$STOCK_SHA256" ]]; then
  echo "stock driver checksum mismatch" >&2
  echo "expected: $STOCK_SHA256" >&2
  echo "actual:   $ACTUAL_SHA256" >&2
  exit 1
fi
echo "[ok] Stock driver SHA-256 verified"

echo "[*] Applying CV2 patches ..."
mkdir -p "$HERE/prebuilt"
python3 "$HERE/patch_driver.py" "$STOCK" "$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

PATCHED="$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"
ACTUAL_PATCHED_SHA256="$(sha256sum "$PATCHED" | cut -d' ' -f1)"
if [[ "$ACTUAL_PATCHED_SHA256" != "$PATCHED_SHA256" ]]; then
  echo "patched driver checksum mismatch" >&2
  echo "expected: $PATCHED_SHA256" >&2
  echo "actual:   $ACTUAL_PATCHED_SHA256" >&2
  exit 1
fi
echo "[ok] Patched driver SHA-256 verified"

echo "[*] Copying firmware blobs from upstream ..."
mkdir -p "$HERE/firmware"
cp -n "$WORK"/up/var/lib/fprint/fw/* "$HERE/firmware/" 2>/dev/null || true

echo "[*] Done. Now run:  ./install.sh"
