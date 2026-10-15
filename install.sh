#!/usr/bin/env bash
# Install the patched ControlVault2 fingerprint driver and its assets.
# Run from the repository root:  ./install.sh   (uses sudo when not root)
#
# Environment overrides:
#   TOD_DIR=<dir>  directory libfprint loads TOD drivers from (auto-detected)
#   FORCE=1        install even if libfprint does not look TOD-enabled
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"
SO="$HERE/prebuilt/libfprint-2-tod-1-broadcom.PATCHED.so"

[[ -f "$SO" ]] || die "Patched driver not found. Build it first:  ./build_from_upstream.sh"
[[ "$(uname -m)" == x86_64 ]] || die "The Broadcom driver is x86_64-only (this machine: $(uname -m))."
python3 "$HERE/patch_driver.py" --check "$SO" >/dev/null \
  || die "$SO is not a fully patched driver. Re-run ./build_from_upstream.sh"

# --- libfprint must be able to load TOD drivers ------------------------------
if [[ -z "$(find_libfprint_libs)" ]]; then
  warn "libfprint-2 not found. Install fprintd and a TOD-enabled libfprint."
  tod_install_hint
  [[ "${FORCE:-0}" == 1 ]] || exit 1
elif ! libfprint_has_tod; then
  warn "The installed libfprint is not TOD-enabled."
  tod_install_hint
  [[ "${FORCE:-0}" == 1 ]] || exit 1
fi

TOD_DIR="$(detect_tod_dir)" || {
  warn "Could not determine the TOD driver directory."
  die "Re-run with TOD_DIR=<dir>, e.g. TOD_DIR=/usr/lib64/libfprint-2/tod-1 ./install.sh"
}
log "TOD driver directory: $TOD_DIR"

MISSING="$(ldd "$SO" 2>/dev/null | awk '/not found/ {print $1}' || true)"
if [[ -n "$MISSING" ]]; then
  warn "The driver needs libraries that are not installed:"
  echo "$MISSING" | sed 's/^/      /' >&2
  tod_install_hint
  [[ "${FORCE:-0}" == 1 ]] || exit 1
fi

# --- driver ------------------------------------------------------------------
DEST="$TOD_DIR/$DRIVER_NAME"
$SUDO mkdir -p "$TOD_DIR" "$FW_DIR"
# Keep a stock driver installed by a distro package (e.g. libfprint-2-tod1-broadcom)
# so uninstall.sh can put it back.
# Exclude legacy CV2 builds too, so uninstall does not restore an older patched driver.
if [[ -f "$DEST" ]] && ! python3 "$HERE/patch_driver.py" --check --allow-legacy "$DEST" >/dev/null; then
  if [[ ! -f "$BACKUP_DIR/$DRIVER_NAME" ]]; then
    log "Backing up existing $DEST -> $BACKUP_DIR/"
    $SUDO mkdir -p "$BACKUP_DIR"
    $SUDO cp -p "$DEST" "$BACKUP_DIR/$DRIVER_NAME"
    echo "$DEST" | $SUDO tee "$BACKUP_DIR/original-path" >/dev/null
  fi
fi
log "Installing driver -> $DEST"
$SUDO install -m644 "$SO" "$DEST"

log "Installing firmware blobs -> $FW_DIR"
if compgen -G "$HERE/firmware/*" >/dev/null; then
  for f in "$HERE"/firmware/*; do
    [[ "$(basename "$f")" == NOTICE.txt ]] && continue
    [[ -e "$FW_DIR/$(basename "$f")" ]] || $SUDO install -m644 "$f" "$FW_DIR/"
  done
fi

# SELinux (Fedora, openSUSE with SELinux): give the new files the policy's label.
if command -v restorecon >/dev/null; then
  $SUDO restorecon -F "$DEST" "$FW_DIR" 2>/dev/null || true
fi

# --- udev --------------------------------------------------------------------
log "Installing udev rule -> $UDEV_DIR/$UDEV_RULE"
$SUDO mkdir -p "$UDEV_DIR"
$SUDO install -m644 "$HERE/udev/$UDEV_RULE" "$UDEV_DIR/$UDEV_RULE"
$SUDO rm -f "$LEGACY_UDEV_DIR/$UDEV_RULE"
$SUDO udevadm control --reload-rules
# "add" (not the default "change") so rules that only match on add also run.
$SUDO udevadm trigger --action=add --subsystem-match=usb \
  --attr-match=idVendor="$USB_VID" --attr-match=idProduct="$USB_PID" || true

log "Restarting fprintd"
$SUDO systemctl restart fprintd 2>/dev/null || true

if [[ -z "$(find_cv2_usb)" ]]; then
  warn "No USB device $USB_VID:$USB_PID found. Is the fingerprint reader enabled in the BIOS?"
fi

echo
echo "Done. Next:"
echo "  fprintd-enroll        # enroll your finger (press, lift, repeat)"
echo "  fprintd-verify        # test recognition"
echo "  sudo pam-auth-update  # (Debian/Ubuntu, optional) enable fingerprint login / sudo"
echo
echo "If fprintd says \"No devices available\" or enrollment fails, run ./diagnose.sh"
echo "and attach its output to a GitHub issue."
