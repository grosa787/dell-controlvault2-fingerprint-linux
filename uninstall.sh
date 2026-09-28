#!/usr/bin/env bash
# Remove the patched driver and assets. Your enrolled prints live on the chip;
# remove them first with: fprintd-delete "$USER"
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"

DIRS=("${TOD_DIR_CANDIDATES[@]}")
if d="$(detect_tod_dir)"; then DIRS=("$d" "${DIRS[@]}"); fi

for d in $(printf '%s\n' "${DIRS[@]}" | awk '!seen[$0]++'); do
  f="$d/$DRIVER_NAME"
  [[ -f "$f" ]] || continue
  # Recognize both current and legacy CV2 builds; leave stock/unknown drivers alone.
  if python3 "$HERE/patch_driver.py" --check --allow-legacy "$f" >/dev/null; then
    log "Removing $f"
    $SUDO rm -f "$f"
  else
    log "Keeping $f (not the patched CV2 driver)"
  fi
done

if [[ -f "$BACKUP_DIR/$DRIVER_NAME" ]]; then
  orig="$(cat "$BACKUP_DIR/original-path" 2>/dev/null || true)"
  if [[ -n "$orig" && ! -e "$orig" ]]; then
    log "Restoring original driver -> $orig"
    $SUDO install -m644 "$BACKUP_DIR/$DRIVER_NAME" "$orig"
  fi
  $SUDO rm -rf "$BACKUP_DIR"
fi

$SUDO rm -f "$UDEV_DIR/$UDEV_RULE" "$LEGACY_UDEV_DIR/$UDEV_RULE"
$SUDO udevadm control --reload-rules
$SUDO udevadm trigger --action=change --subsystem-match=usb \
  --attr-match=idVendor="$USB_VID" --attr-match=idProduct="$USB_PID" || true
$SUDO systemctl restart fprintd 2>/dev/null || true
echo "Removed. (Firmware blobs in $FW_DIR left in place; delete manually if desired.)"
