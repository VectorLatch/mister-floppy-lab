#!/usr/bin/env python3
"""Append Bart CPU raw bus-state fields to on-demand Main v1 snapshot reader.

Use after scripts/patch_bart_main_snapshot_v1.py against pinned
Physical Floppy Main 1.3. No new routine floppy SPI requests and no
disk request, disk data, floppy DMA or interrupt handling changes.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s, old, new, name):
    found = s.count(old)
    if found != 1:
        raise RuntimeError(f"{name}: expected one anchor, found {found}")
    return s.replace(old, new, 1)

def apply(root):
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != PINNED:
        raise RuntimeError(f"Expected Physical-Floppy Main {PINNED}, got {actual}")
    path = root / "user_io.cpp"
    s = path.read_text()
    if "bart_snapshot_poll()" not in s:
        raise RuntimeError("Apply v1 Main snapshot patch before v2")

    s = once(s, "sig != 0xB4A6", "sig != 0xB4A7", "signature")
    s = once(s, "uint16_t v[30]={};", "uint16_t v[40]={};", "buffer length")
    s = once(s, "for(unsigned i=1;i<30;i++)", "for(unsigned i=1;i<40;i++)", "SPI word count")
    s = once(s, "if(v[1]!=1)", "if(v[1]!=2)", "protocol version")
    # Insert one extra fprintf after the eight 32-bit Paula counters are read;
    # field widths and names are stable and compare between separate samples.
    anchor = """    fputc('\\n',out);
    fclose(out);
}
"""
    before = """    uint32_t busaddr=((uint32_t)v[31]<<16)|v[30];
    uint32_t hist2=((uint32_t)v[35]<<16)|v[34];
    uint32_t hist3=((uint32_t)v[37]<<16)|v[36];
    uint32_t buscycles=((uint32_t)v[39]<<16)|v[38];
    fprintf(out, " RAW_BUS=%08X BUSFLAGS=%04X BUSDETAIL=%04X"
            " FETCH_OLD2=%06X FETCH_OLD3=%06X BUS_EVENTS=%u",
            busaddr, v[32], v[33], hist2, hist3, buscycles);
"""
    s = once(s, anchor, before + anchor, "append CPU bus state")
    path.write_text(s)
    print("Applied v2 CPU bus reader: B4A7 version 2, 40 words.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: patch_bart_main_cpu_bus_v2.py <Physical Main source>")
    apply(Path(sys.argv[1]).resolve())
