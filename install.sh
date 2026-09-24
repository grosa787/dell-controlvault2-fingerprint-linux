#!/usr/bin/env bash
# Install the patched ControlVault2 fingerprint driver (prebuilt) and its assets.
# Run from the repository root:  sudo ./install.sh   (or ./install.sh, it will sudo)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TOD_DIR=/usr/lib/x86_64-linux-gnu/libfprint-2/tod-1
FW_DIR=/var/lib/fprint/fw
RULES_DIR=/usr/lib/udev/rules.d
LEGACY_RULES_DIR=/lib/udev/rules.d
RULE=61-broadcom-cv2-5834.rules
SO="$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

if [[ ! -f "$SO" ]]; then
  echo "Prebuilt driver not found. Build it first:  ./build_from_upstream.sh" >&2
  exit 1
fi

# Reject stale or modified build artifacts before any system changes.
python3 - "$HERE" "$SO" <<'PY'
import hashlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from patch_driver import PATCHED_SHA256
if hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest() != PATCHED_SHA256:
    sys.exit("driver checksum mismatch; run ./build_from_upstream.sh before installing")
PY

# NOTICE.txt alone is not firmware.
firmware=()
for f in "$HERE"/firmware/*; do
  if [[ -f "$f" && "${f##*/}" != NOTICE.txt ]]; then
    firmware+=("$f")
  fi
done
if (( ${#firmware[@]} == 0 )); then
  echo "Firmware blobs not found. Build them first:  ./build_from_upstream.sh" >&2
  exit 1
fi

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

echo "[*] Installing driver -> $TOD_DIR"
$SUDO mkdir -p "$TOD_DIR" "$FW_DIR"
$SUDO install -m644 "$SO" "$TOD_DIR/libfprint-2-tod-1-broadcom.so"

echo "[*] Installing firmware blobs -> $FW_DIR"
$SUDO install -m644 "${firmware[@]}" "$FW_DIR"/

echo "[*] Installing udev rule -> $RULES_DIR"
$SUDO install -D -m644 "$HERE/udev/$RULE" "$RULES_DIR/$RULE"
# Remove a copy left by older versions, unless /lib is an alias of /usr/lib.
if [[ -e "$LEGACY_RULES_DIR/$RULE" && ! "$LEGACY_RULES_DIR" -ef "$RULES_DIR" ]]; then
  $SUDO rm -f "$LEGACY_RULES_DIR/$RULE"
fi
$SUDO udevadm control --reload-rules
$SUDO udevadm trigger --subsystem-match=usb --attr-match=idVendor=0a5c \
  --attr-match=idProduct=5834 --action=add

echo "[*] Restarting fprintd"
$SUDO systemctl restart fprintd || true

echo
echo "Done. Next:"
echo "  fprintd-enroll        # enroll your finger (press, lift, repeat)"
echo "  fprintd-verify        # test recognition"
echo "  sudo pam-auth-update  # (optional) enable fingerprint login / sudo"
