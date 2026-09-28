# Regression tests

Run the checks that do not require a vendor binary:

```bash
python3 -m unittest discover -s tests -v
```

Binary integration tests are skipped unless you supply the stock library from
the exact Canonical revision pinned in `build_from_upstream.sh`:

```bash
CV2_STOCK_DRIVER=/absolute/path/to/stock/libfprint-2-tod-1-broadcom.so \
  python3 -m unittest discover -s tests -v
```

Full tests require x86-64 Linux, Python 3, Bash, a C compiler (`cc`), and the
vendor library's runtime dependencies (including TOD-enabled libfprint).
The stock input must have SHA-256
`54fa3befc02df393077cebf96e018e3bf752cee61509897d945ab18c58c5e172`.
The integration tests require stock input. The patcher itself also accepts its
exact patched output for idempotent re-patching; other modified inputs are
rejected. The upstream library path is
`usr/lib/x86_64-linux-gnu/libfprint-2/tod-1/libfprint-2-tod-1-broadcom.so`.

The C harnesses load a temporary patched library and intercept downstream calls;
no USB device, fingerprint scans, root privileges or running `fprintd` service
are required. They exercise enrollment-update error handling, verify/identify reporting,
and delete authorization/status propagation. Other checks cover
commit pointers and error branching, expected output checksum, unchanged output
on invalid input, rejection of modified stock libraries, and rejection of stale
libraries before installation. Atomic-write tests check
replacement without modifying the previous inode, preservation of the existing
output on write/replace failure, and temporary-file cleanup. Additional checks
cover `--check` on stock and nine-patch builds, rejection of legacy builds for
new installations, and idempotent re-patching (including in place). The invalid
input installer test intercepts system commands and checks that invalid input
is rejected before they run.

`test_driver_lifecycle.py` exercises installation, upgrade, removal and stock
backup restoration in temporary directories. System paths and device probes
are redirected to fixtures; service, udev and dependency commands are stubbed.
It checks that `--check --allow-legacy` recognizes the exact old five-patch build
for removal and backup decisions, while stock, partial, unknown and modified
builds remain protected from removal. Legacy builds remain invalid as the new
installation source. No system driver or service is changed by these tests.

The harness addresses and call conventions are specific to the pinned binary.
Their success does not replace physical enrollment, negative matching checks,
or testing persistence after reboot. Do not commit vendor binaries or USB traces
as fixtures.

The identify harness also checks that error statuses cannot reuse a stale match,
that retry errors are reported before completion, and that session cleanup runs.

The enrollment harness does not execute the full enrollment state machine.
The commit checks inspect encoded arguments and the error branch; they do not
execute the commit wrapper or validate its complete calling convention.

Build-script regression tests run without network access or a vendor binary:

```bash
python3 -m unittest discover -s tests -p test_build_from_upstream.py -v
```

These tests cover the pinned fetch revision, firmware replacement, and
temporary-directory cleanup on success and on fetch, patch, or copy failures.
Missing firmware retains the main branch's warning behavior. Git and the
patcher use local fixtures; filesystem operations use the actual shell commands.

## Hardware validation

The contributor reports successful enrollment, authenticated deletion, and
verification/login after a full reboot on a Latitude 7490. An unenrolled finger
was also tested and rejected. These results apply to that tested unit; broader
hardware coverage and multi-finger identify validation remain pending.
