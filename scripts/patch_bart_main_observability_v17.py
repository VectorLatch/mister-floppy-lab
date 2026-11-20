#!/usr/bin/env python3
"""Main v17: atomic host-observable blitter activity, independent of v16 wait mode."""
from pathlib import Path
import subprocess
import sys
PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise ValueError(f"{label}: wanted one anchor, got {n}")
    return s.replace(a,b,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED: raise ValueError("Wrong pinned Main source "+sha)
    path=root/"user_io.cpp"
    s=path.read_text()
    if "bart_v16_blitter_poll();" not in s or "bart_v15_tune_poll();" not in s:
        raise ValueError("Apply v11/v14/v15/v16 Main patches first")
    block=r'''
// v17 SPI interface: read-only diagnostics (independent of v16 mode).
// EC7F returns version C717; EC00 latches atomic snapshot; EC01 clears;
// EC20..EC2D returns 14 frozen 16-bit words; EC2E returns snapshot seq.
// Seven 32-bit values: starts, CPU blitter writes, writes while busy,
// CPU chip/slow RAM while busy, v16 wait candidates, CPU cycles, busy ticks.
static uint16_t bart_v17_spi_word(uint16_t command)
{
    EnableFpga();
    spi_w(command);
    spi_w(0);
    uint16_t out=spi_w(0);
    DisableFpga();
    return out;
}
static bool bart_v17_get_counters(uint32_t values[7],uint16_t *seq)
{
    if(bart_v17_spi_word(0xEC7F)!=0xC717) return false;
    uint16_t before=bart_v17_spi_word(0xEC2E);
    uint16_t response=bart_v17_spi_word(0xEC00);
    if(response!=0xC700) return false;
    uint16_t after=bart_v17_spi_word(0xEC2E);
    if((uint16_t)(after-before)!=1) return false; // snapshot actually triggered
    for(int i=0;i<7;i++) {
        uint16_t lo=bart_v17_spi_word((uint16_t)(0xEC20+2*i));
        uint16_t hi=bart_v17_spi_word((uint16_t)(0xEC21+2*i));
        values[i]=(uint32_t)lo | ((uint32_t)hi<<16);
    }
    if(bart_v17_spi_word(0xEC2E)!=after) return false; // snapshot stable
    *seq=after;
    return true;
}
static void bart_v17_diagnostics_poll()
{
    static unsigned long next_check=0;
    if(next_check && !CheckTimer(next_check))return;
    next_check=GetTimer(500);
    FILE *f=fopen("/tmp/bart-v17-diagnostics.req","r");
    if(!f)return;
    char req[64]={};
    bool have=!!fgets(req,sizeof(req),f);
    fclose(f);
    unlink("/tmp/bart-v17-diagnostics.req");
    FILE *out=fopen("/tmp/bart-v17-diagnostics.last","w");
    if(!out)return;
    if(!have) {
        fprintf(out,"ERROR BART_V17 empty request\n");
        fclose(out);return;
    }
    bool clear=!strncmp(req,"clear",5);
    if(!clear && strncmp(req,"snapshot",8) && strncmp(req,"status",6)) {
        fprintf(out,"ERROR BART_V17 expected clear, snapshot, or status\n");
        fclose(out);return;
    }
    if(bart_v17_spi_word(0xEC7F)!=0xC717) {
        fprintf(out,"ERROR BART_V17 wrong FPGA signature; no changes made\n");
        fclose(out);return;
    }
    if(clear && bart_v17_spi_word(0xEC01)!=0xC701) {
        fprintf(out,"ERROR BART_V17 clear command wasn't acknowledged\n");
        fclose(out);return;
    }
    uint32_t values[7]={};
    uint16_t seq=0;
    if(!bart_v17_get_counters(values,&seq)) {
        fprintf(out,"ERROR BART_V17 snapshot sequence or version verification failed; do not trust results\n");
        fclose(out);return;
    }
    fprintf(out,
        "OK BART_V17 SEQ=%u STARTS=%u BLIT_WRITES=%u BUSY_WRITES=%u RAM_WHILE_BUSY=%u WAIT_CANDIDATES=%u CPU_CYCLES=%u BUSY_TICKS=%u\n",
        (unsigned)seq,
        (unsigned)values[0],(unsigned)values[1],(unsigned)values[2],
        (unsigned)values[3],(unsigned)values[4],(unsigned)values[5],
        (unsigned)values[6]);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{","v17 host reader")
    s=once(s,
        "\t\tbart_v16_blitter_poll(); // actual Agnus completion interlock",
        "\t\tbart_v16_blitter_poll(); // actual Agnus completion interlock\n"
        "\t\tbart_v17_diagnostics_poll(); // independent 32-bit counters",
        "add v17 poller")
    path.write_text(s)
    print("Bart v17 Main: EC7F verified version, EC00 atomic snapshot, EC01 clear, EC20..2E counter readout")
    print("No changes to physical floppy Main datapath.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: patch_bart_main_observability_v17.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
