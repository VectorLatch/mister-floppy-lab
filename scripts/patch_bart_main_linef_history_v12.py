#!/usr/bin/env python3
"""Bart v12 on-demand Main decoder for latest/prior Line-F events."""
from pathlib import Path
import subprocess
import sys

PINNED = "d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s, old, new, label):
    if s.count(old) != 1:
        raise ValueError(f"{label}: expected one match; got {s.count(old)}")
    return s.replace(old, new, 1)

def apply(root):
    rev = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if rev != PINNED:
        raise ValueError(f"Wrong pinned Main source: {rev}")
    path = root / "user_io.cpp"
    s = path.read_text()
    if "bart_v11_wait_poll" not in s or "sig != 0xB4AD" not in s:
        raise ValueError("Apply original Main v8 then v11 patches before v12")
    s = once(s, "sig != 0xB4AD", "sig != 0xB4AE", "E7 signature")
    s = once(s, "if(v[1]!=8)", "if(v[1]!=12)", "E7 protocol version")
    begin = "    // v8 repurposes v6 transport indices 45..63 (64 words total):"
    end = "    fputc('\\n',out);"
    a, b = s.find(begin), s.find(end, s.find(begin))
    if a < 0 or b < a or s.count(begin) != 1:
        raise ValueError("Cannot uniquely locate v8 event log formatter")
    block = r"""    // v12 E7 words 45..63: first, most recent, and preceding Line-F.
    // PC is an internal fx68k register sampled at exception recognition.
    const uint32_t lf_first_pc=((uint32_t)v[46]<<16)|v[45];
    const uint32_t lf_last_pc=((uint32_t)v[48]<<16)|v[47];
    const uint32_t lf_last_fetch=((uint32_t)v[50]<<16)|v[49];
    const uint32_t lf_last_prev=((uint32_t)v[52]<<16)|v[51];
    const uint32_t lf_prior_pc=((uint32_t)v[54]<<16)|v[53];
    const uint32_t lf_prior_fetch=((uint32_t)v[56]<<16)|v[55];
    const uint32_t lf_prior_prev=((uint32_t)v[58]<<16)|v[57];
    const uint16_t lf_flags=v[63];
    fprintf(out,
            " LF12_COUNT=%u LF12_FLAGS=%04X LF12_FIRST_PC=%08X"
            " LF12_LAST_PC=%08X LF12_LAST_FETCH=%08X LF12_LAST_PREV=%08X"
            " LF12_PRIOR_PC=%08X LF12_PRIOR_FETCH=%08X LF12_PRIOR_PREV=%08X"
            " LF12_LAST_PSW=%04X LF12_LAST_IR=%04X LF12_PRIOR_IR=%04X"
            " LF12_HAS_LAST=%u LF12_HAS_PRIOR=%u LF12_LAST_OVL=%u"
            " LF12_LIVE_OVL=%u LF12_LIVE_RESET_OUT_LOW=%u"
            " LF12_LAST_RESET_OUT_LOW=%u LF12_COUNT_SATURATED=%u",
            (unsigned)v[62], lf_flags, lf_first_pc,
            lf_last_pc, lf_last_fetch, lf_last_prev,
            lf_prior_pc, lf_prior_fetch, lf_prior_prev,
            v[59], v[60], v[61],
            (unsigned)(lf_flags&1), (unsigned)((lf_flags>>1)&1),
            (unsigned)((lf_flags>>2)&1), (unsigned)((lf_flags>>3)&1),
            (unsigned)((lf_flags>>4)&1), (unsigned)((lf_flags>>5)&1),
            (unsigned)((lf_flags>>6)&1));
"""
    s = s[:a] + block + s[b:]
    if "uint16_t v[64]={};" not in s or "for(unsigned i=1;i<64;i++)" not in s:
        raise ValueError("Expected 64-word E7 reader has changed")
    path.write_text(s)
    print("v12 Main decoder: 64 E7 words, B4AE version 12, v11 waits retained.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_main_linef_history_v12.py <Main root>")
    apply(Path(sys.argv[1]).resolve())
