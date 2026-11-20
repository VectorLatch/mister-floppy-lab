#!/usr/bin/env python3
"""Add one /tmp request that changes E8 base and E9 extra CPU timing knobs.

v11 E8 API and its original /tmp request remain fully supported.
No Main startup polling or normal floppy traffic changes absent a request.
"""
from pathlib import Path
import subprocess
import sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s, a,b,label):
    n=s.count(a)
    if n!=1:raise ValueError(f"{label}: required unique source anchor, got {n}")
    return s.replace(a,b,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PINNED:raise ValueError(f"Expected pinned Main {PINNED}; got {rev}")
    p=root/"user_io.cpp"
    s=p.read_text()
    if "static void bart_v11_wait_poll()" not in s or "bart_v11_wait_poll();" not in s:
        raise ValueError("Apply v11 Main runtime bus waits first")
    block=r'''
// Bart v14: complete CPU-bus tuning request; no changes to floppy paths.
// Each setting is 0..3. Extra controls apply at the next eligible CPU
// bus acknowledgement; use F12 Amiga reset after setting, before game boot.
// Existing v11 E8xx and /tmp/bart-v11-waits.req stay compatible.
static void bart_v14_tune_poll()
{
    static unsigned long next_check=0;
    if (next_check && !CheckTimer(next_check)) return;
    next_check=GetTimer(750);

    FILE *f=fopen("/tmp/bart-v14-tune.req","r");
    if (!f) return;
    int chip=-1,cia=-1,readx=-1,writex=-1,customx=-1,blitx=-1;
    char extra=0;
    int got=fscanf(f,"%d %d %d %d %d %d %c",
                   &chip,&cia,&readx,&writex,&customx,&blitx,&extra);
    fclose(f);
    unlink("/tmp/bart-v14-tune.req");

    FILE *out=fopen("/tmp/bart-v14-tune.last","w");
    if(!out)return;
    if(got!=6 || chip<0 || chip>3 || cia<0 || cia>3 ||
       readx<0 || readx>3 || writex<0 || writex>3 ||
       customx<0 || customx>3 || blitx<0 || blitx>3) {
        fprintf(out,"ERROR BART_V14 expected six integers 0..3: CHIP CIA READ WRITE CUSTOM BLIT\n");
        fclose(out);
        return;
    }

    const uint16_t base=(uint16_t)((cia<<2)|chip);
    const uint16_t ex=(uint16_t)((blitx<<6)|(customx<<4)|
                                 (writex<<2)|readx);
    uint16_t ack8=0,ack9=0;
    // SPI responses can lag one command. Double-write BOTH requests
    // and accept only the second readback, like the proven v11 script.
    for(int n=0;n<2;n++) {
        EnableFpga();
        spi_w(0xE800);
        spi_w(base);
        ack8=spi_w(0);
        DisableFpga();

        EnableFpga();
        spi_w(0xE900);
        spi_w(ex);
        ack9=spi_w(0);
        DisableFpga();
    }
    if(ack8!=(uint16_t)(0xB800|base) ||
       ack9!=(uint16_t)(0xB900|ex)) {
        fprintf(out,"ERROR BART_V14 FPGA ACK mismatch: E8=%04X expected=%04X E9=%04X expected=%04X; do not trust settings\n",
                ack8,0xB800|base,ack9,0xB900|ex);
    } else {
        fprintf(out,"OK BART_V14 CHIP_WAIT=%d CIA_WAIT=%d READ_EXTRA=%d WRITE_EXTRA=%d CUSTOM_EXTRA=%d BLIT_EXTRA=%d FPGA_ACK_E8=%04X FPGA_ACK_E9=%04X (F12 Reset before test)\n",
                chip,cia,readx,writex,customx,blitx,ack8,ack9);
    }
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{",
           "new on-demand v14 poll implementation")
    s=once(s,"\t\tbart_v11_wait_poll();",
           "\t\tbart_v11_wait_poll();\n\t\tbart_v14_tune_poll();",
           "Minimig-only poll hook")
    p.write_text(s)
    print("Added v14 on-demand E8+E9 CPU-bus timing controller (six 0..3 knobs).")
    print("Original v11 timing API preserved; zero traffic in normal use.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_main_tuning_v14.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
