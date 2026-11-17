#!/usr/bin/env python3
"""Matching on-demand Physical-Floppy Main for Bart first RESET/Line-F v8.

Apply after pinned v1/v2/v3/v6 Main patches, NOT v7 decoder.
Only touches the v6 diagnostic output formatter plus signature/version;
E7xx SPI is still requested only for /tmp/bart-snapshot.req.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:
        raise ValueError(f"{label}: expected exactly one anchor found {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:
        raise ValueError(f"Wrong pinned Main source commit {sha}")
    path=root/"user_io.cpp"
    s=path.read_text()
    if "DF_TRACE_FLAGS" not in s or "sig != 0xB4AB" not in s:
        raise ValueError("Apply Main v1/v2/v3/v6 source patches first")

    s=once(s,"sig != 0xB4AB","sig != 0xB4AD","v8 signature")
    s=once(s,"if(v[1]!=6)","if(v[1]!=8)","v8 protocol version")

    begin="    // The first 45 words are the unmodified v1/v2/v3 diagnostic."
    end="    fputc('\\n',out);"
    start=s.find(begin)
    stop=s.find(end,start)
    if start<0 or stop<0 or s.find(begin,start+1)>=0:
        raise ValueError("Could not uniquely locate existing v6 trace formatter")

    block="""    // v8 repurposes v6 transport indices 45..63 (64 words total):
    // first/last RESET PC, last reset fetch history, first Line-F PC and
    // pre-LineF fetch history, PSWs/opcodes, overlay/edge flags.
    uint32_t rst_first_pc=((uint32_t)v[46]<<16)|v[45];
    uint32_t rst_last_pc=((uint32_t)v[48]<<16)|v[47];
    uint32_t rst_fetch=((uint32_t)v[50]<<16)|v[49];
    uint32_t rst_prev=((uint32_t)v[52]<<16)|v[51];
    uint32_t linef_pc=((uint32_t)v[54]<<16)|v[53];
    uint32_t linef_fetch=((uint32_t)v[56]<<16)|v[55];
    uint32_t linef_prev=((uint32_t)v[58]<<16)|v[57];
    const uint16_t flags=v[63];
    fprintf(out, " EV_FLAGS=%04X EV_RESET_COUNT=%u"
            " EV_RESET_SEEN=%u EV_LINEF_SEEN=%u"
            " EV_RESET_OVL=%u EV_LINEF_OVL=%u EV_LINEF_AFTER_RESET=%u"
            " EV_OVL_LIVE=%u EV_RESET_OUT_LOW=%u"
            " EV_RESET_FIRST_PC=%08X EV_RESET_LAST_PC=%08X"
            " EV_RESET_FETCH=%08X EV_RESET_PREV=%08X"
            " EV_RESET_PSW=%04X EV_RESET_IR=%04X"
            " EV_LINEF_PC=%08X EV_LINEF_FETCH=%08X"
            " EV_LINEF_PREV=%08X EV_LINEF_PSW=%04X EV_LINEF_IR=%04X",
            flags, (unsigned)(flags>>8),
            (unsigned)(flags&1), (unsigned)((flags>>1)&1),
            (unsigned)((flags>>2)&1), (unsigned)((flags>>3)&1),
            (unsigned)((flags>>4)&1),
            (unsigned)((flags>>6)&1), (unsigned)((flags>>7)&1),
            rst_first_pc, rst_last_pc, rst_fetch, rst_prev,
            v[60], v[61],
            linef_pc, linef_fetch, linef_prev, v[59], v[62]);
"""
    s=s[:start]+block+s[stop:]
    if "uint16_t v[64]={};" not in s or "for(unsigned i=1;i<64;i++)" not in s:
        raise ValueError("Lost original matched 64-word reader")
    path.write_text(s)
    print("V8 on-demand Main: 64 SPI words B4AD version8, reset+LineF event fields.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_first_reset_linef_v8.py <pinned Main source>")
    apply(Path(sys.argv[1]).resolve())
