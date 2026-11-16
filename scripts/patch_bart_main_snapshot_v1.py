#!/usr/bin/env python3
"""Minimal on-demand Bart FPGA snapshot reader for Physical-Floppy Main v1.3.

Reads no registers during normal boot: user manually requests a snapshot with
touch /tmp/bart-snapshot.req once the emulator has hung. The file check is
rate-limited. Does not log during floppy transfers or modify floppy code.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(src,old,new,label):
    n=src.count(old)
    if n!=1: raise RuntimeError(f"{label}: expected one match, found {n}")
    return src.replace(old,new,1)

def patch(root):
    sha=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if sha!=PINNED: raise RuntimeError(f"wrong Physical Main version: {sha}")
    file=root/"user_io.cpp"
    s=file.read_text()
    block=r'''
// Bart experimental read-only FPGA snapshot: invoked *only* by requesting
// /tmp/bart-snapshot.req. No polling of the FPGA during disk loading.
static uint16_t bart_snapshot_word(unsigned reg)
{
    EnableFpga();
    spi_w((uint16_t)(0xE700 | reg));
    spi_w(0);
    uint16_t result = spi_w(0);
    DisableFpga();
    return result;
}
static void bart_snapshot_poll()
{
    static unsigned long next_check=0;
    if (next_check && !CheckTimer(next_check)) return;
    next_check=GetTimer(750);
    struct stat st;
    if (stat("/tmp/bart-snapshot.req", &st)) return;
    unlink("/tmp/bart-snapshot.req");

    // First confirm matching FPGA protocol. DO NOT sample other cores.
    const uint16_t sig=bart_snapshot_word(0);
    FILE *out=fopen("/tmp/bart-snapshots.txt", "a");
    if (!out) return;
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    unsigned long long t=(unsigned long long)ts.tv_sec*1000000ULL +
                         (unsigned long long)ts.tv_nsec/1000ULL;
    if (sig != 0xB4A6) {
        fprintf(out, "%llu ERROR non-diagnostic FPGA SIG=%04X\n", t, sig);
        fclose(out);
        return;
    }
    uint16_t v[30]={};
    v[0]=sig;
    for(unsigned i=1;i<30;i++) v[i]=bart_snapshot_word(i);
    if(v[1]!=1) {
        fprintf(out,"%llu ERROR protocol version=%u\n",t,v[1]);
        fclose(out);
        return;
    }
    uint32_t fetch=((uint32_t)v[9]<<16)|v[8];
    uint32_t last=((uint32_t)v[11]<<16)|v[10];
    uint32_t prev=((uint32_t)v[13]<<16)|v[12];
    fprintf(out,"%llu SIG=%04X VER=%u FLAGS=%04X SYNC=%04X LEN=%04X TRACK=%u FIFO=%u DMASTATE=%u"
            " CPU_FETCHES=%u FETCH_LAST=%08X FETCH_PREV=%08X",
            t,v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],fetch,last,prev);
    const char *names[8]={
        "dma_arms","dma_done","sync_irqs","flux_sync_events",
        "dmal_cycles","dsklen_writes","active_fifo_empty_cycles","read_cycles"
    };
    for(unsigned k=0;k<8;k++){
        uint32_t count=((uint32_t)v[15+k*2]<<16)|v[14+k*2];
        fprintf(out," %s=%u",names[k],count);
    }
    fputc('\n',out);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{","snapshot implementation")
    s=once(s,
        "\t\tpfloppy_amiga_poll();\n\t\tUpdateDriveStatus();",
        "\t\tpfloppy_amiga_poll();\n\t\tUpdateDriveStatus();\n\t\tbart_snapshot_poll();",
        "Minimig Main callsite")
    file.write_text(s)
    print("On-demand diagnostic reader patched into Main v1.3.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_main_snapshot_v1.py <pinned Physical Main source>")
    patch(Path(sys.argv[1]))
