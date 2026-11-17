#!/usr/bin/env python3
"""v10 ECS A500+ matching Main readout of two scanline-locked bitplane traces.

Apply AFTER v1/v2/v3/v6/v8/v9 Main patches to pinned Physical Floppy Main.
No autonomous SPI polling or behaviour changes outside explicit snapshot.
"""
from pathlib import Path
import subprocess
import sys
PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,before,after,label):
    n=s.count(before)
    if n!=1: raise RuntimeError(f"{label}: expected 1 anchor, found {n}")
    return s.replace(before,after,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise RuntimeError(f"Wrong pinned Main SHA {sha}")
    p=root/"user_io.cpp"; s=p.read_text()
    if "GFX_OCS_PENDING_TICKS" not in s or "sig != 0xB4AE" not in s:
        raise RuntimeError("Apply v9 diagnostic Main patch first")
    s=once(s,"sig != 0xB4AE","sig != 0xB4AF","v10 signature")
    s=once(s,"if(v[1]!=9)","if(v[1]!=10)","v10 version")
    start=s.find("    // v9 FPGA graphics diagnostics: raw 16-bit bus words 45..63.")
    end=s.find("    fputc('\\n',out);",start)
    if start<0 or end<0 or s.find("    // v9 FPGA graphics diagnostics:",start+1)>=0:
        raise RuntimeError("Cannot locate v9 data formatter")
    block=r'''    // v10 two-scanline, same-source ECS/A500+ graphics telemetry.
    // v=0x080 (128) and v=0x0E0 (224) Agnus raster lines.
    // First BPL1DAT word is captured at actual Denise 'data16' load,
    // other three planes are their most recent BPLxDAT holding words.
    // Separately report first Agnus BPL1 DMA pointer (word address);
    // DO NOT assume pointer/data capture are cycle-aligned.
    const uint16_t modes=v[45];
    const uint32_t hash_a=((uint32_t)v[49]<<16)|v[48];
    const uint32_t hash_b=((uint32_t)v[51]<<16)|v[50];
    const uint32_t ptr_a=((((uint32_t)modes)&15)<<16)|v[60];
    const uint32_t ptr_b=((uint32_t)((modes>>4)&15)<<16)|v[61];
    fprintf(out, " V10_ECS=%u V10_AGA=%u V10_DMA_A_VALID=%u V10_DMA_B_VALID=%u"
            " V10_LINE_A=128 V10_LINE_B=224"
            " V10_A_HITS=%u V10_B_HITS=%u V10_A_HASH=%08X V10_B_HASH=%08X"
            " V10_A_P1=%04X V10_A_P2=%04X V10_A_P3=%04X V10_A_P4=%04X"
            " V10_B_P1=%04X V10_B_P2=%04X V10_B_P3=%04X V10_B_P4=%04X"
            " V10_A_FIRST_DMA_BYTE_ADDR=%06X V10_B_FIRST_DMA_BYTE_ADDR=%06X"
            " V10_BPLCON0=%04X V10_BPLCON1=%04X",
            (unsigned)((modes>>11)&1), (unsigned)((modes>>10)&1),
            (unsigned)((modes>>9)&1), (unsigned)((modes>>8)&1),
            (unsigned)v[46], (unsigned)v[47], hash_a, hash_b,
            v[52],v[53],v[54],v[55],v[56],v[57],v[58],v[59],
            (unsigned)(ptr_a<<1), (unsigned)(ptr_b<<1),
            v[62],v[63]);
'''
    s=s[:start]+block+s[end:]
    if "for(unsigned i=1;i<64;i++)" not in s:
        raise RuntimeError("Existing 64-word on-demand read lost")
    p.write_text(s)
    print("Paired v10 Main reader: B4AF v10, ECS config and 2 scanline data traces.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_main_words_v10.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
