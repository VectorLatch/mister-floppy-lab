#!/usr/bin/env python3
"""Bart v9 paired Physical Floppy Main: decode FPGA graphics slots 45..63.

Preserves v1/v2/v3 snapshot output and all on-demand request semantics.
No background SPI polling, floppy datapath changes, or CPU memory reads.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise RuntimeError(f"{label}: expected one anchor, got {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise RuntimeError(f"Wrong pinned Main SHA {sha}")
    p=root/"user_io.cpp"
    s=p.read_text()
    if "EV_LINEF_PC" not in s or "sig != 0xB4AD" not in s or "uint16_t v[64]={};" not in s:
        raise RuntimeError("v9 Main must follow v1/v2/v3/v6/v8 patches")
    s=once(s,"sig != 0xB4AD","sig != 0xB4AE","v9 signature")
    s=once(s,"if(v[1]!=8)","if(v[1]!=9)","v9 version")
    begin="    // v8 repurposes v6 transport indices 45..63 (64 words total):"
    end="    fputc('\\n',out);"
    a=s.find(begin)
    b=s.find(end,a)
    if a<0 or b<0 or s.find(begin,a+1)>=0:
        raise RuntimeError("Could not uniquely locate v8 formatter")
    block=r'''    // v9 FPGA graphics diagnostics: raw 16-bit bus words 45..63.
    // Counters update continuously after core reset but SPI reads happen
    // ONLY on /tmp/bart-snapshot.req; two readings show rates/deltas.
    // Do not confuse the raw DMA bus tap with the actual Denise word.
    const uint16_t gfxflags=v[45];
    const uint32_t dmaslots=((uint32_t)v[49]<<16)|v[48];
    const uint32_t bpl1writes=((uint32_t)v[51]<<16)|v[50];
    const uint32_t ocssnaps=((uint32_t)v[53]<<16)|v[52];
    const uint32_t pendingticks=((uint32_t)v[55]<<16)|v[54];
    const uint32_t legacyticks=((uint32_t)v[57]<<16)|v[56];
    const uint32_t lastaddr=(((uint32_t)v[61]&0xF)<<16)|v[60];
    fprintf(out,
            " GFX_FLAGS=%04X GFX_BPLCON0=%04X GFX_BPLCON1=%04X"
            " GFX_DMA_SLOTS=%u GFX_BPL1DAT=%u GFX_OCS_SNAPSHOTS=%u"
            " GFX_OCS_PENDING_TICKS=%u GFX_OCS_LEGACY_TICKS=%u"
            " GFX_OCS_IMMEDIATE=%u GFX_OCS_DELAYED=%u"
            " GFX_LAST_DMA_BYTE_ADDR=%06X GFX_LAST_DMA_BUS=%04X"
            " GFX_DMA_WRITES=%u",
            gfxflags,v[46],v[47],
            dmaslots,bpl1writes,ocssnaps,
            pendingticks,legacyticks,
            v[58],v[59],
            (unsigned)(lastaddr<<1),v[62],v[63]);
'''
    s=s[:a]+block+s[b:]
    if "for(unsigned i=1;i<64;i++)" not in s:
        raise RuntimeError("Lost on-demand 64-word FPGA reader")
    p.write_text(s)
    print("Patched on-demand Bart Main for graphics read-only SPI B4AE v9.")
    print("Existing v1/v2/v3 CPU/Paula diagnostic slots 0..44 preserved.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_graphics_v9.py <pinned Main source>")
    apply(Path(sys.argv[1]).resolve())
