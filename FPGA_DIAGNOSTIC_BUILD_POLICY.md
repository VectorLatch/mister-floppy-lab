# FPGA diagnostic build-artifact policy

**Default for all future Minimig/Bart experimental FPGA workflows.**

## Never discard a successfully compiled FPGA because timing failed

A completed Quartus Full Compilation with a nonempty `.rbf` must be **archived before enforcing the strict timing gate**, even if the static timing result is negative. This policy avoids wasting a complete FPGA compilation when a research bitstream is still useful for comparative hardware experiments.

1. Run Quartus and require a successfully completed full compilation (zero errors), with a nonempty `.rbf`.
2. **Before any timing-failure exit**, archive the compiled `.rbf`, SHA-256 checksum, pinned source SHA, fitter seed and build ID, all five timing-slack values and status `PASS`, `FAIL` or `UNKNOWN`. Include Quartus logs and timing reports.
3. Keep the strict timing gate: any negative or missing margin must make the workflow **fail** rather than falsely declaring a timing-clean build.
4. The upload-artifact step must run using `if: always()` so failed timing does not suppress artifact publication. Do not archive nonexistent/partial binaries after an actual compilation error.
5. For hardware diagnostics, enable explicit **`--allow-timing-fail`** installation *only* when (a) Quartus compiled successfully, (b) the matching ARM Main passed, (c) only the timing gate failed, (d) reported status is exactly `FAIL` (not `UNKNOWN`), (e) hashes/run/source IDs match, and (f) the user knowingly opts in. A timing-failed build is never to be advertised as release-safe.
6. Preserve previous bitstreams, a matching Main and rollback copies of `MiSTer.ini`. Do not overwrite the known-working Rick Dangerous FPGA.
7. Use only the chosen fitter seed per build unless specifically asked for multiple; do not launch multiple seeds to chase timing automatically.

## Reusable implementation

The tested workflow pattern (first introduced in Bart v8/seed 6) is:

- `scripts/package-bart-diagnostic-fpga.py package ...` **before** timing gate, writes `TIMING-STATUS.json`, `TIMING-STATUS.txt`, `.rbf` and `.sha256`.
- `scripts/package-bart-diagnostic-fpga.py gate --status-file dist/TIMING-STATUS.json` fails the workflow when timing is not strictly positive.
- GitHub `actions/upload-artifact@v4` with `if: always()` includes `dist/*` plus timing reports.
- `scripts/verify-bart-diagnostic-build.py` authorizes timing-failed experimental installation only with `--allow-timing-fail` and only if failure was **exclusively** the designated timing-check step.
- The v8 installer `scripts/deploy-bart-first-reset-linef-v8.sh` demonstrates clean vs timing-failed invocation.

Canonical files are maintained on branch `diagnostic/bart-first-reset-linef-v8` in this repository. Any new diagnostic branch/workflow must include or reuse them, not copy the old pattern that generates the `.rbf` only after passing timing.

### Important limitation

A missing or corrupt bitstream or an unsuccessful Quartus compilation is **not** a timing-only failure; it cannot safely be installed. An experimental bitstream that compiled but did not meet static timing may execute unreliably, so observations from it require independent confirmation on a timing-clean build before claiming a functional fix.

See GitHub issue #1 for the current Bart Disk 2 investigation (distinct from earlier Disk 1 Ocean-screen tests).
