#!/usr/bin/env python3
"""Matching on-demand v5 Main reader for CPU last-two fault history.

Read-only FPGA SPI B4AA version 5; uses same 60 words as v4.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected 1 anchor found {n}")
    return s.replace(old,new,1)

def apply(root):
    actual=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if actual!=PINNED: raise ValueError(f"Wrong upstream Main {actual}")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "FX_FAULT1_ADDR" not in s or "sig != 0xB4A9" not in s:
        raise ValueError("Apply pinned Main v1-v4 patches first")
    s=once(s,"sig != 0xB4A9","sig != 0xB4AA","signature")
    s=once(s,"if(v[1]!=4)","if(v[1]!=5)","protocol version")
    start_marker="    uint32_t fault1addr="
    end_marker="    fputc('\\n',out);"
    start=s.find(start_marker)
    end=s.find(end_marker,start)
    if start<0 or end<0 or s.find(start_marker,start+1)>=0:
        raise ValueError("Cannot uniquely locate previous v4 output section")
    section="""    // Slots unchanged from v4: index 45 count, 46..52 prior event,
    // 53..59 most recent event. UADDR [13:10] now includes group0.
    uint32_t prev_addr=((uint32_t)v[47]<<16)|v[46];
    uint32_t prev_pc=((uint32_t)v[49]<<16)|v[48];
    uint32_t last_addr=((uint32_t)v[54]<<16)|v[53];
    uint32_t last_pc=((uint32_t)v[56]<<16)|v[55];
    fprintf(out, " FX_ADDRERR_EPISODES=%u"
            " FX_PREV_ADDR=%08X FX_PREV_PC=%08X"
            " FX_PREV_PSW=%04X FX_PREV_IRD=%04X"
            " FX_PREV_UADDR=%03X FX_PREV_GRP0=%X"
            " FX_LAST_ADDR=%08X FX_LAST_PC=%08X"
            " FX_LAST_PSW=%04X FX_LAST_IRD=%04X"
            " FX_LAST_UADDR=%03X FX_LAST_GRP0=%X",
            v[45], prev_addr, prev_pc, v[50], v[51],
            v[52]&0x03FF, (v[52]>>10)&0x0F,
            last_addr, last_pc, v[57], v[58],
            v[59]&0x03FF, (v[59]>>10)&0x0F);
"""
    s=s[:start]+section+s[end:]
    path.write_text(s)
    print("Applied v5 read-only on-demand 60-word Main; B4AA version 5.")
    print("Prints penultimate/latest address error and group0 sequencer flags.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_last_address_fault_v5.py <Main source>")
    apply(Path(sys.argv[1]).resolve())
