#!/usr/bin/env python3
"""Decode on-demand B4AC/v7 64-word CPU vector 3 bus-input snapshot.

Overlay AFTER existing pinned Main v1,v2,v3,v6 source-only read patches.
Does not alter routine floppy SPI, DMA or data paths.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected one source match, found {n}")
    return s.replace(old,new,1)

def apply(root):
    actual=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if actual!=PINNED: raise ValueError(f"Unexpected upstream Main {actual}")
    p=root/"user_io.cpp"
    s=p.read_text()
    if "DF_TRACE_FLAGS" not in s or "sig != 0xB4AB" not in s:
        raise ValueError("Apply pinned Main v1/v2/v3/v6 patches first")

    s=once(s,"sig != 0xB4AB","sig != 0xB4AC","v7 matching signature")
    s=once(s,"if(v[1]!=6)","if(v[1]!=7)","v7 matching SPI protocol")

    start_marker="    // The first 45 words are the unmodified v1/v2/v3 diagnostic."
    end_marker="    fputc('\\n',out);"
    start=s.find(start_marker)
    end=s.find(end_marker,start)
    if start<0 or end<0 or s.find(start_marker,start+1)>=0:
        raise ValueError("Could not uniquely identify v6 DF trace printing block")
    block="""    // V7 reuses the 64-register v6 transport for the last CPU bus
    // samples at address-error vector #3 high/low words ($C/$E).
    // C/E samples are from the exact cpu_din net feeding fx68k.iEdb
    // on an asserted AS, read strobes, DTACK and enPhi2 sampling edge.
    uint32_t vec_c_bus=((uint32_t)v[46]<<16)|v[45];
    uint32_t vec_e_bus=((uint32_t)v[48]<<16)|v[47];
    uint32_t vec_df_bus=((uint32_t)v[50]<<16)|v[49];
    uint32_t vec_df_first=((uint32_t)v[52]<<16)|v[51];
    uint32_t vec_c_pc=((uint32_t)v[54]<<16)|v[53];
    uint32_t vec_e_pc=((uint32_t)v[56]<<16)|v[55];
    uint16_t vec_c_data=v[58];
    uint16_t vec_e_data=v[57];
    uint16_t vec_c_meta=v[60];
    uint16_t vec_e_meta=v[59];
    uint32_t vec_pointer=((uint32_t)vec_c_data<<16)|vec_e_data;
    fprintf(out, " VEC_FLAGS=%04X VEC_C_COUNT=%u VEC_E_COUNT=%u"
            " VEC_C_DATA=%04X VEC_E_DATA=%04X VEC_ASSEMBLED=%08X"
            " VEC_C_META=%04X VEC_E_META=%04X"
            " VEC_C_PC=%08X VEC_E_PC=%08X"
            " VEC_C_BUS_EVT=%u VEC_E_BUS_EVT=%u"
            " VEC_DF_BUS_EVT=%u VEC_DF_FIRST=%08X",
            v[63], v[61], v[62],
            vec_c_data, vec_e_data, vec_pointer,
            vec_c_meta, vec_e_meta,
            vec_c_pc, vec_e_pc,
            vec_c_bus, vec_e_bus, vec_df_bus, vec_df_first);
"""
    s=s[:start]+block+s[end:]
    if "uint16_t v[64]={};" not in s or "for(unsigned i=1;i<64;i++)" not in s:
        raise ValueError("64-word on-demand Main reader was not retained")
    p.write_text(s)
    print("Applied paired v7 Main vector-read decoder, 64 SPI words B4AC version 7.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_address_vector_reads_v7.py <pinned Main source>")
    apply(Path(sys.argv[1]).resolve())
