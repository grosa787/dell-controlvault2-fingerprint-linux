#!/usr/bin/env bash
# Remove the patched driver and assets. Your enrolled prints live on the chip;
# remove them first with: fprintd-delete "$USER"
set -euo pipefail
RULE=61-broadcom-cv2-5834.rules
SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"
$SUDO rm -f /usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so
# Current location, plus the one used by older versions on non-merged-/usr systems.
$SUDO rm -f "/usr/lib/udev/rules.d/$RULE" "/lib/udev/rules.d/$RULE"
$SUDO udevadm control --reload-rules
$SUDO udevadm trigger --subsystem-match=usb --attr-match=idVendor=0a5c \
  --attr-match=idProduct=5834
$SUDO systemctl restart fprintd || true
echo "Removed. (Firmware blobs in /var/lib/fprint/fw left in place; delete manually if desired.)"
