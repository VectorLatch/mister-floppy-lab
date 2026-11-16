#!/usr/bin/env python3
"""Main user_io.cpp v4 on-demand fault recorder reader.

Layer AFTER Main v1/v2/v3 patches. No disk datapath changes.
"""
from pathlib import Path
import subprocess,sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    if s.count(old)!=1: raise ValueError(f"{label}: expected 1 anchor found {s.count(old)}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise ValueError(f"Wrong Main version: {sha}")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "FX_HALT" not in s or "sig != 0xB4A8" not in s:
        raise ValueError("Apply Main v1, v2, and v3 patches first")
    s=once(s,"sig != 0xB4A8","sig != 0xB4A9","v4 signature")
    s=once(s,"uint16_t v[45]={};","uint16_t v[60]={};","v4 register buffer")
    s=once(s,"for(unsigned i=1;i<45;i++)","for(unsigned i=1;i<60;i++)","v4 register count")
    s=once(s,"if(v[1]!=3)","if(v[1]!=4)","v4 protocol")
    line="""    uint32_t fault1addr=((uint32_t)v[47]<<16)|v[46];
    uint32_t fault1pc=((uint32_t)v[49]<<16)|v[48];
    uint32_t fault2addr=((uint32_t)v[54]<<16)|v[53];
    uint32_t fault2pc=((uint32_t)v[56]<<16)|v[55];
    fprintf(out, " FX_FAULT_COUNT=%u"
            " FX_FAULT1_ADDR=%08X FX_FAULT1_PC=%08X"
            " FX_FAULT1_PSW=%04X FX_FAULT1_IRD=%04X FX_FAULT1_UADDR=%03X"
            " FX_FAULT2_ADDR=%08X FX_FAULT2_PC=%08X"
            " FX_FAULT2_PSW=%04X FX_FAULT2_IRD=%04X FX_FAULT2_UADDR=%03X",
            v[45], fault1addr, fault1pc, v[50], v[51], v[52],
            fault2addr, fault2pc, v[57], v[58], v[59]);
"""
    tail="""    fputc('\\n',out);
    fclose(out);
}
"""
    s=once(s,tail,line+tail,"append v4 address fault records")
    path.write_text(s)
    print("Main on-demand v4 reads B4A9 v4, 60 words, appends two fault records.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_main_first_address_fault_v4.py <pinned Main source>")
    apply(Path(sys.argv[1]).resolve())
