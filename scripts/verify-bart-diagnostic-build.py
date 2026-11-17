#!/usr/bin/env python3
"""Validate a Bart FPGA diagnostic run for experimental MiSTer installation.

A clean build is installed normally. If (and ONLY if) the sole job failure
was the strict timing gate and the compiled binary was archived with valid
checksums and TIMING_STATUS=FAIL, allow it with --allow-timing-fail.

This is intended to be reused by future Bart diagnostic installers. It
does not silence GitHub timing failures or reclassify them as successful.
"""
import argparse
import json
import subprocess
from pathlib import Path

def api(path):
    return json.loads(subprocess.check_output(
        ["gh", "api", path], text=True
    ))

def error(msg):
    raise SystemExit("Build verification refused: " + msg)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--branch", required=True)
    p.add_argument("--workflow", required=True)
    p.add_argument("--status-json", required=True)
    p.add_argument("--fpga-binary", required=True)
    p.add_argument("--allow-timing-fail", action="store_true")
    args = p.parse_args()

    run = api(f"repos/{args.repo}/actions/runs/{args.run}")
    if run.get("status") != "completed":
        error("GitHub Actions run is not completed")
    if run.get("head_branch") != args.branch:
        error("Wrong GitHub branch")
    if run.get("path", "").lstrip("./") != args.workflow.lstrip("./"):
        error("Wrong GitHub workflow")
    jobs = api(f"repos/{args.repo}/actions/runs/{args.run}/jobs?per_page=100").get("jobs", [])
    fpga = [j for j in jobs if j.get("name", "").startswith("Rick-fixed ")]
    main_jobs = [j for j in jobs if j.get("name", "").startswith("Physical Floppy Main")]
    if len(fpga) != 1 or len(main_jobs) != 1:
        error("Expected exactly one FPGA and one matching Physical Floppy Main job")
    fj, mj = fpga[0], main_jobs[0]
    if mj.get("conclusion") != "success":
        error("Matching ARM Main job did not succeed")
    if fj.get("status") != "completed":
        error("FPGA job is not complete")

    status_path = Path(args.status_json)
    if not status_path.is_file():
        error("TIMING-STATUS.json was not archived in the FPGA artifact")
    status = json.loads(status_path.read_text())
    if status.get("schema") != 1 or status.get("experimental_only") is not True:
        error("Unexpected artifact timing manifest")
    if str(status.get("run_id")) != str(run["id"]):
        error("Artifact run ID does not match the GitHub build")
    if status.get("source_sha") != run.get("head_sha"):
        error("Artifact source SHA does not match the GitHub build")
    if status.get("fpga_bitstream") != args.fpga_binary:
        error("Artifact FPGA filename does not match the requested build")
    if not status.get("verified_full_compilation"):
        error("Quartus full compilation was not verified")
    import hashlib
    binary = status_path.parent / args.fpga_binary
    if not binary.is_file() or binary.stat().st_size == 0:
        error("Missing compiled FPGA bitstream")
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != status.get("bitstream_sha256"):
        error("FPGA checksum does not match archived timing manifest")

    kind = status.get("timing_status")
    if kind == "PASS":
        if fj.get("conclusion") != "success" or run.get("conclusion") != "success":
            error("Timing marked PASS but GitHub run was not successful")
        if any(x is None or x < 0 for x in status.get(
            "setup_hold_recovery_removal_min_pulse_slack_ns", {}
        ).values()):
            error("Timing marked PASS but a recorded margin was negative or missing")
        print("Verified: FPGA and Main successful, all timing margins passed, artifact matches this run.")
    elif kind == "FAIL":
        if not args.allow_timing_fail:
            error("FPGA timing FAIL — rerun installer with --allow-timing-fail to opt in to experimental testing")
        failed = [s.get("name", "") for s in fj.get("steps", []) if s.get("conclusion") == "failure"]
        if len(failed) != 1 or failed[0] != "Strict timing gate - require nonnegative worst-case slack on all categories":
            error("FPGA failure was not exclusively the expected strict timing gate")
        if fj.get("conclusion") != "failure" or run.get("conclusion") != "failure":
            error("Timing-failed diagnostic has an unexpected GitHub run/job conclusion")
        slacks = status.get("setup_hold_recovery_removal_min_pulse_slack_ns", {})
        if len(slacks) != 5 or any(x is None for x in slacks.values()) or all(x >= 0 for x in slacks.values()):
            error("TIMING_STATUS=FAIL but five negative/nonnegative recorded margins are inconsistent")
        print("WARNING: FPGA HAS A VERIFIED STATIC TIMING VIOLATION.", flush=True)
        print("WARNING: This test result is experimental and cannot prove correctness.", flush=True)
        print("Verified: only strict timing gate failed; Main succeeded; binary and manifest match this run.")
    else:
        error("Timing status UNKNOWN, or missing; refusing installation")

if __name__ == "__main__":
    main()
