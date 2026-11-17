#!/usr/bin/env python3
"""Reusable Bart FPGA diagnostic artifact policy.

Always package a successfully compiled .rbf and its SHA-256, regardless of
timing closure; separately record a machine-readable strict timing verdict.
The --gate command marks the workflow FAILED if timing is not PASS, *after*
packaging. Installers must explicitly opt in to a TIMING_FAIL bitstream.
Never package a partial, absent, or zero-byte bitstream.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

CATEGORIES = ("setup", "hold", "recovery", "removal", "minimum pulse width")

def assess(log_text):
    slacks = {}
    for name in CATEGORIES:
        regex = r"(?im)Worst-case\s+" + re.escape(name) + r"\s+slack\s+is\s+([+-]?\d+(?:\.\d+)?)"
        values = [float(v) for v in re.findall(regex, log_text)]
        slacks[name] = min(values) if values else None
    if any(v is None for v in slacks.values()):
        verdict = "UNKNOWN"
    elif any(v < 0 for v in slacks.values()):
        verdict = "FAIL"
    else:
        verdict = "PASS"
    return verdict, slacks

def package(args):
    source = Path(args.binary)
    compile_log = Path(args.compile_log)
    if not source.is_file() or source.stat().st_size == 0:
        raise SystemExit("No valid compiled FPGA bitstream; cannot package an unusable build")
    if not compile_log.is_file() or compile_log.stat().st_size == 0:
        raise SystemExit("Missing compile log; cannot validate build")
    log = compile_log.read_text(errors="replace")
    # Require actual successful Quartus full compilation, not merely the
    # presence of a stale bitstream file in output_files.
    if not re.search(r"Quartus Prime Full Compilation was successful\.\s*0 errors", log):
        raise SystemExit("Full Quartus compilation was not verified successful")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / args.name
    shutil.copyfile(source, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    (out / (args.name + ".sha256")).write_text(f"{digest}  {args.name}\n")
    status, slacks = assess(log)
    data = {
        "schema": 1,
        "timing_status": status,
        "verified_full_compilation": True,
        "all_five_categories_required": True,
        "setup_hold_recovery_removal_min_pulse_slack_ns": slacks,
        "fitter_seed": args.seed,
        "run_id": args.run_id,
        "source_sha": args.source_sha,
        "fpga_bitstream": args.name,
        "bitstream_sha256": digest,
        "experimental_only": True,
        "safe_for_release": status == "PASS",
        "message": ("Timing met all reported requirements" if status == "PASS" else
                    "Experimental bitstream retained; timing did NOT pass strict gate")
    }
    (out / "TIMING-STATUS.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    (out / "TIMING-STATUS.txt").write_text(
        "TIMING_STATUS=" + status + "\n" +
        "EXPERIMENTAL_ONLY=1\n" +
        "".join(f"{name}={slacks[name]} ns\n" for name in CATEGORIES) +
        "This is a research bitstream, not a timing-certified release.\n"
    )
    for name, value in slacks.items():
        print(f"{name}: {value if value is not None else 'NOT REPORTED'} ns")
    print(f"FPGA artifact preserved: {dest} (SHA-256 {digest})")
    print(f"TIMING_STATUS={status}")
    if status != "PASS":
        print("::warning::Quartus compiled but timing was not confirmed clean; bitstream is retained for explicitly opted-in testing")

def gate(args):
    data = json.loads(Path(args.status_file).read_text())
    status = data.get("timing_status")
    if status == "PASS":
        print("Strict FPGA timing gate PASSED (all five margins >= 0 ns)")
        return
    raise SystemExit(f"Strict FPGA timing gate FAILED: TIMING_STATUS={status}; "
                     "bitstream and reports were already preserved in the artifact")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    pkg = sub.add_parser("package", help="retain .rbf/checksum/timing even when timing fails")
    pkg.add_argument("--binary", required=True)
    pkg.add_argument("--compile-log", required=True)
    pkg.add_argument("--out", required=True)
    pkg.add_argument("--name", required=True)
    pkg.add_argument("--seed", type=int, required=True)
    pkg.add_argument("--run-id", required=True)
    pkg.add_argument("--source-sha", required=True)
    check = sub.add_parser("gate", help="fail workflow if any margin is negative or missing")
    check.add_argument("--status-file", required=True)
    args = parser.parse_args()
    if args.action == "package":
        package(args)
    else:
        gate(args)

if __name__ == "__main__":
    main()
