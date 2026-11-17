#!/usr/bin/env python3
"""Extend v3 on-demand Physical Floppy Main snapshot to 64-word V6 trace.

Only changes on-request diagnostic read path. All routine floppy
SPI reads/writes, DMA, timing and emulated CPU logic remain unchanged.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected one source anchor found {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if sha!=PINNED: raise ValueError(f"Wrong pinned Main {sha}")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "FX_HALT" not in s or "sig != 0xB4A8" not in s:
        raise ValueError("Apply v1, v2, v3 Main diagnostic patches first")

    s=once(s,"sig != 0xB4A8","sig != 0xB4AB","v6 SPI signature")
    s=once(s,"uint16_t v[45]={};","uint16_t v[64]={};","64 word array")
    s=once(s,"for(unsigned i=1;i<45;i++)","for(unsigned i=1;i<64;i++)","64 word reads")
    s=once(s,"if(v[1]!=3)","if(v[1]!=6)","v6 SPI protocol")

    block="""    // The first 45 words are the unmodified v1/v2/v3 diagnostic.
    // Words 45..58: six previous program fetches plus the first DF fetch.
    // Words 59..60: fx68k internal PC at that event.
    // Word 61/62: PSW and IRD; word 63: flags. All on demand.
    uint32_t df_pre0=((uint32_t)v[46]<<16)|v[45];
    uint32_t df_pre1=((uint32_t)v[48]<<16)|v[47];
    uint32_t df_pre2=((uint32_t)v[50]<<16)|v[49];
    uint32_t df_pre3=((uint32_t)v[52]<<16)|v[51];
    uint32_t df_pre4=((uint32_t)v[54]<<16)|v[53];
    uint32_t df_pre5=((uint32_t)v[56]<<16)|v[55];
    uint32_t df_enter=((uint32_t)v[58]<<16)|v[57];
    uint32_t df_pc=((uint32_t)v[60]<<16)|v[59];
    fprintf(out, " DF_TRACE_FLAGS=%04X DF_PRE0=%08X DF_PRE1=%08X"
            " DF_PRE2=%08X DF_PRE3=%08X DF_PRE4=%08X DF_PRE5=%08X"
            " DF_FIRST=%08X DF_PC=%08X DF_PSW=%04X DF_IRD=%04X",
            v[63], df_pre0, df_pre1, df_pre2, df_pre3, df_pre4,
            df_pre5, df_enter, df_pc, v[61], v[62]);
"""
    tail="""    fputc('\\n',out);
    fclose(out);
}
"""
    s=once(s,tail,block+tail,"append frozen first DF transition trace")
    path.write_text(s)
    print("V6 paired Main reader: B4AB ver6, words0..63, read only when requested.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_first_df_fetch_v6.py <pinned Main source>")
    apply(Path(sys.argv[1]).resolve())
