#!/usr/bin/env python3
"""Matching v13 Bart Main on-demand E7 reader: CPU program-read addresses+data."""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s, old, new, label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected one match, got {n}")
    return s.replace(old,new,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PINNED: raise ValueError(f"Unexpected pinned Main source {rev}")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "bart_v11_wait_poll" not in s or "sig != 0xB4AE" not in s:
        raise ValueError("Apply Main v11 wait control and v12 E7 decoder before v13")
    s=once(s,"sig != 0xB4AE","sig != 0xB4AF","E7 signature")
    s=once(s,"if(v[1]!=12)","if(v[1]!=13)","E7 version")
    begin="    // v12 E7 words 45..63: first, most recent, and preceding Line-F."
    end="    fputc('\\n',out);"
    a,b=s.find(begin),s.find(end,s.find(begin))
    if a<0 or b<a or s.count(begin)!=1:
        raise ValueError("Cannot uniquely locate v12 E7 formatter")
    block=r"""    // v13 E7 words 45..63, read-only event freeze.
    // Three recent *acknowledged program-space reads*, not proven retired
    // instructions. Irc is the *internal* fx68k prefetch latch.
    const uint32_t if_pc=((uint32_t)v[46]<<16)|v[45];
    const uint32_t if_fetch0=((uint32_t)v[48]<<16)|v[47];
    const uint32_t if_fetch1=((uint32_t)v[50]<<16)|v[49];
    const uint32_t if_fetch2=((uint32_t)v[52]<<16)|v[51];
    const uint32_t if_bus_addr=((uint32_t)v[54]<<16)|v[53];
    const uint16_t if_flags=v[63];
    fprintf(out,
            " IF13_COUNT=%u IF13_FLAGS=%04X IF13_PC=%08X"
            " IF13_FETCH0_ADDR=%08X IF13_FETCH0_DATA=%04X"
            " IF13_FETCH1_ADDR=%08X IF13_FETCH1_DATA=%04X"
            " IF13_FETCH2_ADDR=%08X IF13_FETCH2_DATA=%04X"
            " IF13_BUS_ADDR=%08X IF13_BUS_DATA=%04X"
            " IF13_IR=%04X IF13_IRC=%04X IF13_PRIOR_IR=%04X"
            " IF13_HAS_EVENT=%u IF13_HAS_PRIOR=%u"
            " IF13_VALID0=%u IF13_VALID1=%u IF13_VALID2=%u"
            " IF13_RAM0=%u IF13_RAM1=%u IF13_RAM2=%u"
            " IF13_AS_ACTIVE=%u IF13_DTACK_ACTIVE=%u IF13_RW_READ=%u"
            " IF13_FC_PROGRAM=%u IF13_RESET_OUT_LOW=%u"
            " IF13_COUNT_SATURATED=%u IF13_OVERLAY=%u",
            (unsigned)v[61],if_flags,if_pc,
            if_fetch0,v[55],if_fetch1,v[56],if_fetch2,v[57],
            if_bus_addr,v[58],v[59],v[60],v[62],
            (unsigned)(if_flags&1), (unsigned)((if_flags>>1)&1),
            (unsigned)((if_flags>>2)&1), (unsigned)((if_flags>>3)&1),
            (unsigned)((if_flags>>4)&1),
            (unsigned)((if_flags>>5)&1), (unsigned)((if_flags>>6)&1),
            (unsigned)((if_flags>>7)&1),
            (unsigned)((if_flags>>8)&1), (unsigned)((if_flags>>9)&1),
            (unsigned)((if_flags>>10)&1), (unsigned)((if_flags>>11)&1),
            (unsigned)((if_flags>>12)&1), (unsigned)((if_flags>>13)&1),
            (unsigned)((if_flags>>14)&1));
"""
    s=s[:a]+block+s[b:]
    if "uint16_t v[64]={};" not in s or "for(unsigned i=1;i<64;i++)" not in s:
        raise ValueError("Expected E7 64-word transport changed")
    path.write_text(s)
    print("v13 Main E7 B4AF / version13: matched CPU instruction-bus data reader.")
    print("v11 on-demand E8xx runtime bus waits retained.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_instruction_fetch_v13.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
