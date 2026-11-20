#!/usr/bin/env python3
"""Bart v16 Main runtime blitter completion safety controls.

Apply to pinned Main after all v15 patches. Uses EB00/EB01 write,
EBF0..EBF4 read-only status. Main must verify the exact v16 FPGA.
"""
from pathlib import Path
import subprocess
import sys
PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"

def once(s,a,b,label):
    n=s.count(a)
    if n!=1:raise ValueError(f"{label}: expected one anchor, found {n}")
    return s.replace(a,b,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise ValueError("Wrong pinned Main "+sha)
    path=root/"user_io.cpp"
    s=path.read_text()
    if "bart_v15_tune_poll();" not in s or "bart_v15_read_slot" not in s:
        raise ValueError("Must apply v15 Main patch before v16")
    block=r'''
// Bart v16: EB00 mode (0=off, 1=BLTSIZE-only, 2=all blitter CPU writes)
// EB01 timeout, in units of 256 7MHz ticks (~36.6us each).
// EBF0..EBF4 read-only: mode, timeout, hit count, completed count, expired.
static bool bart_v16_read_slot(int slot,unsigned *value)
{
    if(slot<0 || slot>4)return false;
    uint16_t r=0;
    for(int n=0;n<2;n++) {
        EnableFpga();
        spi_w((uint16_t)(0xEBF0|slot));
        spi_w(0);
        r=spi_w(0);
        DisableFpga();
    }
    if((r & 0xFF00)!=(uint16_t)(0xB600+(slot<<8)))return false;
    *value=(unsigned)(r&0xFF);
    return true;
}
static void bart_v16_write_slot(int slot,unsigned value)
{
    EnableFpga();
    spi_w((uint16_t)(0xEB00|slot));
    spi_w((uint16_t)value);
    spi_w(0);
    DisableFpga();
}
static bool bart_v16_read_all(unsigned *s)
{
    for(int i=0;i<5;i++)
        if(!bart_v16_read_slot(i,&s[i]))return false;
    return true;
}
static bool bart_v16_parse_prev(const char *text,unsigned *mode,unsigned *timeout)
{
    int m,t;char extra;
    if(sscanf(text,"%d %d %c",&m,&t,&extra)!=2 ||
       m<0 || m>2 || t<1 || t>255)return false;
    *mode=(unsigned)m;
    *timeout=(unsigned)t;
    return true;
}
static void bart_v16_store_prev(unsigned mode,unsigned timeout)
{
    FILE *f=fopen("/tmp/bart-v16-blitter.previous","w");
    if(f) {
        fprintf(f,"%u %u\n",mode,timeout);
        fclose(f);
    }
}
static void bart_v16_blitter_poll()
{
    static unsigned long next_check=0;
    if(next_check && !CheckTimer(next_check))return;
    next_check=GetTimer(500);
    FILE *f=fopen("/tmp/bart-v16-blitter.req","r");
    if(!f)return;
    char req[128]={};
    bool have=!!fgets(req,sizeof(req),f);
    fclose(f);
    unlink("/tmp/bart-v16-blitter.req");
    FILE *out=fopen("/tmp/bart-v16-blitter.last","w");
    if(!out)return;
    if(!have){fprintf(out,"ERROR BART_V16 empty request\n");fclose(out);return;}
    unsigned current[5]={};
    if(!bart_v16_read_all(current)) {
        fprintf(out,"ERROR BART_V16 FPGA does not expose the expected EB register protocol; no change\n");
        fclose(out);return;
    }
    if(!strncmp(req,"status",6)) {
        fprintf(out,"OK BART_V16 MODE=%u TIMEOUT=%u HITS=%u COMPLETE=%u EXPIRED=%u",
                current[0],current[1],current[2],current[3],current[4]);
        fprintf(out," (counters wrap at 255; one timeout unit=256 7MHz ticks)\n");
        fclose(out);return;
    }
    unsigned mode=0,timeout=current[1];
    if(!strncmp(req,"off",3)) {
        mode=0;
    } else if(!strncmp(req,"restore",7)) {
        FILE *pf=fopen("/tmp/bart-v16-blitter.previous","r");
        char line[128]={};
        bool ok=pf && fgets(line,sizeof(line),pf);
        if(pf)fclose(pf);
        if(!ok || !bart_v16_parse_prev(line,&mode,&timeout)) {
            fprintf(out,"ERROR BART_V16 previous verified profile unavailable\n");
            fclose(out);return;
        }
    } else if(!bart_v16_parse_prev(req,&mode,&timeout)) {
        fprintf(out,"ERROR BART_V16 expects mode 0/1/2 and timeout 1..255, or status/off/restore\n");
        fclose(out);return;
    }

    bart_v16_write_slot(0,mode);
    bart_v16_write_slot(1,timeout);
    unsigned newmode=999,newtimeout=999;
    if(!bart_v16_read_slot(0,&newmode) ||
       !bart_v16_read_slot(1,&newtimeout) ||
       mode!=newmode || timeout!=newtimeout) {
        // Revert both live values; still require independent follow-up read.
        bart_v16_write_slot(0,current[0]);
        bart_v16_write_slot(1,current[1]);
        unsigned rm=999,rt=999;
        bool rolled=bart_v16_read_slot(0,&rm) &&
                    bart_v16_read_slot(1,&rt) &&
                    rm==current[0] && rt==current[1];
        fprintf(out,"ERROR BART_V16 register readback mismatch (rollback %s)\n",
                rolled?"verified":"NOT VERIFIED");
        fclose(out);return;
    }
    bart_v16_store_prev(current[0],current[1]);
    unsigned status[5]={};
    if(!bart_v16_read_all(status)) {
        fprintf(out,"ERROR BART_V16 could not read diagnostics after verified setting (mode/timeout were verified)\n");
        fclose(out);return;
    }
    fprintf(out,"OK BART_V16 MODE=%u TIMEOUT=%u HITS=%u COMPLETE=%u EXPIRED=%u VERIFIED=2/2; F12 Reset Amiga before testing\n",
            status[0],status[1],status[2],status[3],status[4]);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{","v16 request handler")
    s=once(s,
        "\t\tbart_v15_tune_poll(); // all v15 controls are 8-bit",
        "\t\tbart_v15_tune_poll(); // all v15 controls are 8-bit\n"
        "\t\tbart_v16_blitter_poll(); // actual Agnus completion interlock",
        "add v16 handler to poll")
    path.write_text(s)
    print("Bart v16 Main: EB00/EB01 mode/timeout, EBF0..EBF4 verified readback and counters.")
    print("v15 controls and original physical-floppy processing retained.")
if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: patch_bart_main_blitter_v16.py <pinned main root>")
    apply(Path(sys.argv[1]).resolve())
