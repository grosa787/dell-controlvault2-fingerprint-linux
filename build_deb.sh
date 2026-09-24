#!/usr/bin/env bash
# Build a .deb that installs the patched CV2 fingerprint driver + firmware +
# udev rule. No debhelper needed: assembles a package tree and calls
# dpkg-deb directly.
#
# Prereq: ./build_from_upstream.sh must have produced prebuilt/ and firmware/.
# This script runs it for you if anything is missing.
#
# Usage:   ./build_deb.sh [outfile.deb]
# Install: sudo dpkg -i "./<outfile.deb>"
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="libfprint-2-tod1-broadcom-cv2"
VERSION="1.0.6-2"
ARCH="amd64"
OUT="${1:-$HERE/${PKG}_${VERSION}_${ARCH}.deb}"

SO="$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"
FW_DIR_SRC="$HERE/firmware"
UDEV="$HERE/udev/61-broadcom-cv2-5834.rules"

# Make sure build artifacts exist (NOTICE.txt alone is not firmware).
have_firmware=false
for f in "$FW_DIR_SRC"/*; do
  if [[ -f "$f" && "${f##*/}" != NOTICE.txt ]]; then
    have_firmware=true
    break
  fi
done
if [[ ! -f "$SO" ]] || [[ "$have_firmware" == false ]]; then
  echo "[*] Build artifacts missing; running ./build_from_upstream.sh first ..."
  (cd "$HERE" && ./build_from_upstream.sh)
fi
[[ -f "$SO" ]] || { echo "prebuilt .so still missing after build" >&2; exit 1; }

# Reject stale or modified build artifacts before packaging.
python3 - "$HERE" "$SO" <<'PY'
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from patch_driver import PATCHED_SHA256
if hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest() != PATCHED_SHA256:
    sys.exit("driver checksum mismatch; run ./build_from_upstream.sh before packaging")
PY

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

# Package layout:
#   usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so
#   var/lib/fprint/fw/<firmware blobs>
#   usr/lib/udev/rules.d/61-broadcom-cv2-5834.rules
TOD="usr/lib/x86_64-linux-gnu/libfprint-2/tod-1"
FW="var/lib/fprint/fw"
RULES="usr/lib/udev/rules.d"

install -d "$STAGE/$TOD" "$STAGE/$FW" "$STAGE/$RULES" "$STAGE/DEBIAN"

install -m644 "$SO"        "$STAGE/$TOD/libfprint-2-tod-1-broadcom.so"
install -m644 "$UDEV"      "$STAGE/$RULES/61-broadcom-cv2-5834.rules"
# Ship every firmware blob except the NOTICE file.
for f in "$FW_DIR_SRC"/*; do
  [[ -f "$f" ]] || continue
  case "$(basename "$f")" in NOTICE.txt) continue;; esac
  install -m644 "$f" "$STAGE/$FW/"
done

cat >"$STAGE/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: non-free/utils
Priority: optional
Architecture: $ARCH
Depends: libfprint-2-tod1, fprintd, udev
Conflicts: libfprint-2-tod1-broadcom
Replaces: libfprint-2-tod1-broadcom
Maintainer: Local build <local@localhost>
Description: Patched Broadcom ControlVault2 fingerprint TOD driver for libfprint
 Makes the Dell ControlVault2 / Broadcom BCM5880 fingerprint reader
 (USB 0a5c:5834) work under fprintd by patching Dell/Canonical's proprietary
 libfprint-2-tod-1-broadcom driver. Ships the patched driver, the CV3
 firmware blobs the driver expects to find, and a udev rule binding the device.
 .
 The driver and firmware are proprietary Dell/Canonical/Broadcom artifacts;
 only the packaging scripts are original work. Use on hardware you own.

EOF

cat >"$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger --subsystem-match=usb --attr-match=idVendor=0a5c \
    --attr-match=idProduct=5834 --action=add || true
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl try-restart fprintd || true
fi
echo
echo "[*] CV2 fingerprint driver installed. Next:"
echo "    fprintd-enroll        # enroll a finger (press, lift, repeat)"
echo "    fprintd-verify        # test recognition"
echo "    sudo pam-auth-update  # (optional) enable fingerprint login / sudo"
EOF
chmod 0755 "$STAGE/DEBIAN/postinst"

cat >"$STAGE/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
if command -v udevadm >/dev/null 2>&1; then
  udevadm control --reload-rules || true
  udevadm trigger --subsystem-match=usb --attr-match=idVendor=0a5c \
    --attr-match=idProduct=5834 || true
fi
if command -v systemctl >/dev/null 2>&1; then
  systemctl try-restart fprintd || true
fi
true
EOF
chmod 0755 "$STAGE/DEBIAN/postrm"

echo "[*] Building .deb ..."
dpkg-deb --build --root-owner-group "$STAGE" "$OUT"

echo "[*] Done: $OUT"
echo
echo "Install with:   sudo dpkg -i \"$OUT\""
echo "Uninstall with: sudo apt remove $PKG"
