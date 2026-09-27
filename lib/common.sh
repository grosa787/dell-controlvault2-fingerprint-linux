# Shared helpers for install.sh / uninstall.sh / diagnose.sh. Source, don't run.
# shellcheck disable=SC2034  # variables are used by the scripts that source this
# shellcheck shell=bash

DRIVER_NAME=libfprint-2-tod-1-broadcom.so
FW_DIR=/var/lib/fprint/fw
BACKUP_DIR=/var/lib/fprint/cv2-backup
UDEV_RULE=61-broadcom-cv2-5834.rules
UDEV_DIR=/etc/udev/rules.d
# Older versions of install.sh put the rule here.
LEGACY_UDEV_DIR=/lib/udev/rules.d
USB_VID=0a5c
USB_PID=5834

# TOD driver directories used by the distros we have reports from:
#   Debian/Ubuntu/Mint     /usr/lib/x86_64-linux-gnu/libfprint-2/tod-1
#   Fedora/openSUSE        /usr/lib64/libfprint-2/tod-1
#   Arch/CachyOS (AUR)     /usr/lib/libfprint-2/tod-1
TOD_DIR_CANDIDATES=(
  /usr/lib/x86_64-linux-gnu/libfprint-2/tod-1
  /usr/lib64/libfprint-2/tod-1
  /usr/lib/libfprint-2/tod-1
)

SUDO=""; [[ $EUID -ne 0 ]] && SUDO="sudo"

log()  { echo "[*] $*"; }
warn() { echo "[!] $*" >&2; }
die()  { echo "[x] $*" >&2; exit 1; }

# Print every libfprint-2 / libfprint-2-tod shared library on the system, one per line.
find_libfprint_libs() {
  {
    ldconfig -p 2>/dev/null | awk '/libfprint-2(-tod)?\.so/ {print $NF}'
    ls /usr/lib/x86_64-linux-gnu/libfprint-2*.so* /usr/lib64/libfprint-2*.so* \
       /usr/lib/libfprint-2*.so* 2>/dev/null
  } | while read -r f; do [[ -e "$f" ]] && readlink -f "$f"; done | sort -u
}

# Succeeds if the installed libfprint can load TOD (third-party) drivers.
# A plain libfprint (e.g. Fedora's) ignores the tod-1 directory entirely and
# logs "No driver found for USB device 0A5C:5834".
libfprint_has_tod() {
  local f
  for f in $(find_libfprint_libs); do
    [[ "$f" == *libfprint-2-tod.so* ]] && return 0
    grep -aqE 'TOD entry point|libfprint-2/tod-1' "$f" 2>/dev/null && return 0
  done
  return 1
}

# Print the TOD driver directory libfprint will scan.
# Order: $TOD_DIR override, path compiled into libfprint, first existing candidate.
detect_tod_dir() {
  if [[ -n "${TOD_DIR:-}" ]]; then echo "$TOD_DIR"; return 0; fi
  local f d
  for f in $(find_libfprint_libs); do
    d=$(grep -aoE '/[[:alnum:]_./+-]*libfprint-2/tod-1' "$f" 2>/dev/null | head -n1 || true)
    if [[ -n "$d" ]]; then echo "$d"; return 0; fi
  done
  for d in "${TOD_DIR_CANDIDATES[@]}"; do
    if [[ -d "$d" ]]; then echo "$d"; return 0; fi
  done
  return 1
}

# Hints printed when libfprint has no TOD support.
tod_install_hint() {
  cat >&2 <<'EOF'
    Your libfprint cannot load TOD drivers, so fprintd will keep reporting
    "No devices available". Install a TOD-enabled libfprint first:
      Debian / Ubuntu / Mint : sudo apt install libfprint-2-tod1
      openSUSE               : sudo zypper install libfprint-2-tod1
      Arch / CachyOS         : AUR package "libfprint-tod"
      Fedora                 : the official libfprint is built without TOD;
                               a TOD-enabled build is needed (not provided here).
    If you are sure TOD is available, re-run with FORCE=1 (and TOD_DIR=<dir>).
EOF
}

# Print the sysfs directory of every connected 0a5c:5834 device.
find_cv2_usb() {
  local d
  for d in /sys/bus/usb/devices/*; do
    [[ -f "$d/idVendor" && -f "$d/idProduct" ]] || continue
    [[ "$(cat "$d/idVendor")" == "$USB_VID" && "$(cat "$d/idProduct")" == "$USB_PID" ]] && echo "$d"
  done
  return 0
}
