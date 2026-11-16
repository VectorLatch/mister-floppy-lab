#!/usr/bin/env python3
"""Read fx68k internal halt/microaddr/status/exception snapshot v3.

Extends previously installed (v1 then v2) one-shot reader only.
Does not touch unrelated Main routines or disk/pulses.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    if s.count(old)!=1:
        raise ValueError(f"{label}: expected one anchor found {s.count(old)}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if sha!=PINNED: raise ValueError("Wrong Physical-Floppy Main source commit")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "FETCH_OLD2" not in s or "0xB4A7" not in s:
        raise ValueError("Apply Main v1 and Main CPU Bus v2 patches before v3")
    s=once(s,"sig != 0xB4A7","sig != 0xB4A8","v3 FPGA signature")
    s=once(s,"uint16_t v[40]={};","uint16_t v[45]={};","read buffer")
    s=once(s,"for(unsigned i=1;i<40;i++)","for(unsigned i=1;i<45;i++)","read word count")
    s=once(s,"if(v[1]!=2)","if(v[1]!=3)","FPGA protocol version")
    tail = """    fputc('\\n',out);
    fclose(out);
}
"""
    line = """    fprintf(out, " FX_HALT=%u FX_UADDR=%03X FX_PSW=%04X FX_IRD=%04X FX_ERR=%02X",
            v[40]&1, v[41], v[42], v[43], v[44]&255);
"""
    s=once(s,tail,line+tail,"append internal status")
    path.write_text(s)
    print("Paired read-only CPU internal v3 Main reader protocol B4A8 version 3, 45 words.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_main_fx68k_internal_v3.py <pinned Physical Main>")
    apply(Path(sys.argv[1]).resolve())
