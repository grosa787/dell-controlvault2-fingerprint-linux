#!/usr/bin/env bash
# Collect the information needed for a bug report. Read-only: changes nothing.
#   ./diagnose.sh                  # print report
#   ./diagnose.sh > report.txt     # save it, review it, attach it to an issue
# Your login name is replaced with <user> in the fprintd log excerpt.
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/common.sh
. "$HERE/lib/common.sh"

section() { printf '\n=== %s ===\n' "$*"; }

section "System"
( . /etc/os-release 2>/dev/null && echo "distro:  ${PRETTY_NAME:-unknown}" )
echo "kernel:  $(uname -r) ($(uname -m))"
if [[ -r /sys/class/dmi/id/product_name ]]; then
  echo "model:   $(cat /sys/class/dmi/id/product_name)"
  echo "bios:    $(cat /sys/class/dmi/id/bios_version 2>/dev/null)"
fi

section "USB device $USB_VID:$USB_PID"
devs="$(find_cv2_usb)"
if [[ -z "$devs" ]]; then
  echo "NOT FOUND (reader disabled in BIOS, or a different model?)"
  command -v lsusb >/dev/null && lsusb -d "$USB_VID:" 2>/dev/null
else
  for d in $devs; do
    echo "sysfs:     $d"
    echo "product:   $(cat "$d/product" 2>/dev/null)"
    echo "bcdDevice: $(cat "$d/bcdDevice" 2>/dev/null)"
    if command -v udevadm >/dev/null; then
      drv="$(udevadm info -q property -p "$d" 2>/dev/null | grep '^LIBFPRINT_DRIVER=' || true)"
      echo "udev:      ${drv:-LIBFPRINT_DRIVER not set (udev rule not applied)}"
    fi
  done
fi

section "libfprint"
libs="$(find_libfprint_libs)"
if [[ -z "$libs" ]]; then
  echo "libfprint-2 NOT FOUND"
else
  echo "$libs"
  if libfprint_has_tod; then echo "TOD support: yes"; else echo "TOD support: NO"; tod_install_hint 2>&1; fi
fi
if command -v dpkg-query >/dev/null; then
  dpkg-query -W 'libfprint-2*' fprintd 2>/dev/null
elif command -v rpm >/dev/null; then
  rpm -qa 'libfprint*' 'fprintd*' 2>/dev/null
elif command -v pacman >/dev/null; then
  pacman -Q 2>/dev/null | grep -E '^(libfprint|fprintd)'
fi

section "Driver"
if tod="$(detect_tod_dir)"; then
  echo "TOD dir: $tod"
  f="$tod/$DRIVER_NAME"
  if [[ -f "$f" ]]; then
    python3 "$HERE/patch_driver.py" --check "$f"
    missing="$(ldd "$f" 2>/dev/null | grep 'not found' || true)"
    [[ -n "$missing" ]] && echo "missing libraries:" && echo "$missing"
  else
    echo "$f NOT INSTALLED (run ./install.sh)"
  fi
else
  echo "TOD dir: not found"
fi
for r in "$UDEV_DIR/$UDEV_RULE" "$LEGACY_UDEV_DIR/$UDEV_RULE"; do
  [[ -f "$r" ]] && echo "udev rule: $r"
done
ls "$FW_DIR" 2>/dev/null | sed 's/^/firmware: /'

section "fprintd log (this boot, relevant lines)"
if command -v journalctl >/dev/null; then
  user="${SUDO_USER:-${USER:-}}"
  $SUDO journalctl -b -u fprintd -o cat --no-pager 2>/dev/null \
    | grep -E 'libfprint version|Opening driver|TOD|5834|No driver|dev_probe|cv_|status|[Ff]ail|[Ee]rror|[Ee]nroll|[Vv]erif|[Ii]dentif|[Cc]ommit|templateHandle|overheat' \
    | grep -v 'GTask' \
    | tail -n 150 \
    | { if [[ -n "$user" ]]; then sed "s/$user/<user>/g"; else cat; fi; }
  echo
  echo "(For a full log enable debug logging first; see README > Troubleshooting.)"
else
  echo "journalctl not available"
fi
