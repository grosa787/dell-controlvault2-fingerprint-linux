#!/usr/bin/env python3
"""
patch_driver.py - turn Dell/Canonical's proprietary ControlVault3 fingerprint
driver (libfprint-2-tod-1-broadcom.so) into one that drives the older
ControlVault2 (Broadcom BCM5880, USB 0a5c:5834) sensor.

It applies 5 byte-level patches by unique signature search (offset-independent),
so it keeps working even if the upstream binary shifts slightly.

Usage:
    python3 patch_driver.py <input.so> <output.so>   apply the patches
    python3 patch_driver.py --check <driver.so>      report which patches are applied

Where <input.so> is the STOCK driver from Canonical's OEM repo:
    git clone -b upstream \\
      https://git.launchpad.net/~oem-solutions-engineers/libfprint-2-tod1-broadcom/+git/libfprint-2-tod1-broadcom
    -> usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so

See PATCHES.md for the full reverse-engineering rationale of every patch.
"""
import hashlib
import sys

# (description, find_bytes, replace_bytes). Each `find` must occur exactly once.
PATCHES = [
    ("1. id_table: add USB PID 0x5834 (was 0x5842) so libfprint binds our device",
     bytes.fromhex("42580000 5c0a0000".replace(" ", "")),
     bytes.fromhex("34580000 5c0a0000".replace(" ", ""))),

    ("2. USB enumerator: accept PID 0x5834 (turn the PID filter `je` into `jmp`)",
     bytes.fromhex("66f7c1fdff 740c".replace(" ", "")),
     bytes.fromhex("66f7c1fdff eb0c".replace(" ", ""))),

    ("3. dev_probe: treat 'cannot determine chip type' (err 0x1c) as success "
     "(CV2 has resident firmware; nothing is flashed)",
     bytes.fromhex("83f81c 741f"),
     bytes.fromhex("83f81c 743a")),

    ("4. enroll: map CV2 'enrollment data ready' status 0x59 to the normal "
     "status-0 path so the template-COMMIT phase runs",
     bytes.fromhex("4181fda4000000 0f84fd010000".replace(" ", "")),
     bytes.fromhex("4181fd59000000 0f84160000 00".replace(" ", ""))),

    ("5. verify: always call verify_report (drop the `edx!=0` short-circuit) so "
     "CV2's non-zero verify status no longer becomes verify-unknown-error",
     bytes.fromhex("85d2 0f858a000000 83f801".replace(" ", "")),
     bytes.fromhex("85d2 909090909090 83f801".replace(" ", ""))),
]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def patch_state(data, find, repl):
    """'stock', 'patched', or 'missing' (signature absent or ambiguous)."""
    n_find, n_repl = data.count(find), data.count(repl)
    if n_find == 1 and n_repl == 0:
        return "stock"
    if n_find == 0 and n_repl == 1:
        return "patched"
    return "missing"


def check(path):
    with open(path, "rb") as f:
        data = f.read()
    print("file:   " + path)
    print("sha256: " + sha256(data))
    states = [patch_state(data, find, repl) for _, find, repl in PATCHES]
    for (desc, _, _), state in zip(PATCHES, states):
        print("[%-7s] %s" % (state, desc.split(":")[0]))
    if all(s == "patched" for s in states):
        print("\nAll %d CV2 patches are applied." % len(PATCHES))
        return 0
    if all(s == "stock" for s in states):
        print("\nThis is the STOCK driver (no CV2 patches).")
        return 1
    print("\nPartially patched or unknown driver build.")
    return 1


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        sys.exit(check(sys.argv[2]))
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    with open(sys.argv[1], "rb") as f:
        data = bytearray(f.read())
    print("input sha256:  " + sha256(data))

    for desc, find, repl in PATCHES:
        assert len(find) == len(repl), "patch length mismatch: " + desc
        state = patch_state(data, find, repl)
        if state == "patched":
            print("[already] " + desc)
            continue
        if state == "missing":
            n = data.count(find)
            if n > 1:
                sys.exit("FAILED: signature ambiguous (%d hits) for patch:\n  %s" % (n, desc))
            sys.exit("FAILED: signature not found for patch:\n  " + desc +
                     "\n  (is this the right libfprint-2-tod-1-broadcom.so?)")
        off = data.index(find)
        data[off:off + len(find)] = repl
        print("[ok] " + desc)

    with open(sys.argv[2], "wb") as f:
        f.write(data)
    print("output sha256: " + sha256(data))
    print("\nPatched driver written to: " + sys.argv[2])


if __name__ == "__main__":
    main()
