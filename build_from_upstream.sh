#!/usr/bin/env bash
# Reproducible build: fetch the STOCK proprietary driver from Canonical's OEM
# repo and apply the CV2 patches locally. This avoids relying on the prebuilt
# binary in this repo (and is the recommended path for a clean GitHub fork).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
UPSTREAM="https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom"

for tool in git python3; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "[*] Cloning upstream (branch: upstream) ..."
git clone --depth 1 -b upstream "$UPSTREAM" "$WORK/up"

STOCK="$WORK/up/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so"
[[ -f "$STOCK" ]] || { echo "stock .so not found in upstream tree" >&2; exit 1; }

echo "[*] Applying CV2 patches ..."
mkdir -p "$HERE/prebuilt"
python3 "$HERE/patch_driver.py" "$STOCK" "$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

echo "[*] Copying firmware blobs from upstream ..."
mkdir -p "$HERE/firmware"
if compgen -G "$WORK/up/var/lib/fprint/fw/*" >/dev/null; then
  cp -f "$WORK"/up/var/lib/fprint/fw/* "$HERE/firmware/"
else
  echo "[!] No firmware blobs found in upstream tree (var/lib/fprint/fw)" >&2
fi

echo "[*] Done. Now run:  ./install.sh"
