#!/usr/bin/env python3
"""Bart v11: on-demand Main interface for live FPGA DTACK wait controls.

Two small integers are written to /tmp/bart-v11-waits.req on the MiSTer
Linux host: <chip_wait> <cia_wait>, each 0..3. On-demand Main poll writes
E800 then value and reads ack. No added SPI traffic on normal startup.
"""
from pathlib import Path
import subprocess,sys

PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,a,b,label):
    n=s.count(a)
    if n!=1:raise RuntimeError(f"{label}: anchor count {n}, expected 1")
    return s.replace(a,b,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise RuntimeError(f"Wrong pinned Main source {sha}")
    p=root/"user_io.cpp"
    s=p.read_text()
    if "sig != 0xB4AD" not in s or "bart_snapshot_poll" not in s:
        raise RuntimeError("Apply original v1/v2/v3/v6/v8 Main reader first")
    block=r'''
// Bart v11 experimental 68000 DTACK waiting knobs. This file is polled
// on the HPS host, not the FPGA. Runtime edits apply until FPGA is reloaded.
// Change only while the emulated Amiga is stopped, then use F12 Reset.
// The default 0,0 is exactly the original unmodified bridge behaviour.
static void bart_v11_wait_poll()
{
    static unsigned long next_check=0;
    if (next_check && !CheckTimer(next_check)) return;
    next_check=GetTimer(750);

    FILE *f=fopen("/tmp/bart-v11-waits.req","r");
    if (!f) return;
    int chip=-1, cia=-1;
    char extra=0;
    int got=fscanf(f,"%d %d %c",&chip,&cia,&extra);
    fclose(f);
    unlink("/tmp/bart-v11-waits.req");

    FILE *out=fopen("/tmp/bart-v11-waits.last","w");
    if (!out) return;
    if(got!=2 || chip<0 || chip>3 || cia<0 || cia>3) {
        fprintf(out,"ERROR invalid waits; expected two integers (chip CIA), both 0..3\n");
        fclose(out);
        return;
    }
    const uint16_t packed=(uint16_t)((cia<<2)|chip);
    // Unused 0xE8xx host opcode, separate from v8 read-only 0xE7xx.
    EnableFpga();
    spi_w(0xE800);
    spi_w(packed);
    const uint16_t reply=spi_w(0);
    DisableFpga();
    if(reply!=(uint16_t)(0xB800|packed))
        fprintf(out,"ERROR FPGA did not acknowledge E8 waits: chip=%d cia=%d, reply=%04X; do not trust configuration\n",chip,cia,reply);
    else
        fprintf(out,"OK BART_V11 CHIP_WAIT=%d CIA_WAIT=%d FPGA_ACK=%04X (reset Amiga via F12 before game test)\n",chip,cia,reply);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{","on-demand config implementation")
    s=once(s,"\t\tbart_snapshot_poll();",
        "\t\tbart_snapshot_poll();\n"
        "\t\tbart_v11_wait_poll();",
        "Minimig-only HPS poll callsite")
    p.write_text(s)
    print("Added Bart v11 on-demand /tmp/bart-v11-waits.req CPU DTACK control.")
    print("No additional SPI operations when no request file is present.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_main_runtime_bus_v11.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
