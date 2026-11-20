#!/usr/bin/env python3
"""Bart v15 Main: verified six-byte live CPU timing and previous/zero restore.

Apply after pinned Main's v11 and v14 patch. The original v11/v14
poll callsites are disabled in v15, to avoid falsely succeeding with
the obsolete 2-bit interface. Read-only SPI E9F0..E9F5 obtains actual
FPGA settings, so state stays accurate across soft/full core resets.
"""
from pathlib import Path
import subprocess
import sys
PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"
def once(s,a,b,name):
    n=s.count(a)
    if n!=1:raise ValueError(f"{name}: expected one anchor, got {n}")
    return s.replace(a,b,1)
def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise ValueError("Wrong pinned Main "+sha)
    path=root/"user_io.cpp"
    s=path.read_text()
    if "bart_v11_wait_poll();" not in s or "bart_v14_tune_poll();" not in s:
        raise ValueError("Expected v11 and v14 Main writers already applied")
    block=r'''
// Bart v15 FPGA command E900..E905 write a full byte of delay;
// E9F0..E9F5 READ the actual FPGA bytes without modifying them.
// Responses are A9xx..AExx; old v14 2-bit E9 replies are B9xx.
// This deliberately FAILS on an incompatible v11/v14 FPGA.
static bool bart_v15_read_slot(int slot, unsigned *value)
{
    if(slot < 0 || slot > 5) return false;
    for(int n=0;n<2;n++) {
        EnableFpga();
        spi_w((uint16_t)(0xE9F0|slot));
        spi_w(0);
        uint16_t r=spi_w(0);
        DisableFpga();
        if ((r & 0xFF00)==(uint16_t)(0xA900|(slot<<8))) {
            *value=(unsigned)(r & 0xFF);
            return true;
        }
    }
    return false;
}
static void bart_v15_write_slot(int slot, unsigned value)
{
    EnableFpga();
    spi_w((uint16_t)(0xE900|slot));
    spi_w((uint16_t)value);
    spi_w(0);
    DisableFpga();
}
static bool bart_v15_all_read(unsigned *values)
{
    for(int i=0;i<6;i++)
        if(!bart_v15_read_slot(i,&values[i])) return false;
    return true;
}
static bool bart_v15_parse_six(const char *s,unsigned *v)
{
    int a[6];char extra;
    int n=sscanf(s,"%d %d %d %d %d %d %c",
                 &a[0],&a[1],&a[2],&a[3],&a[4],&a[5],&extra);
    if(n!=6)return false;
    for(int i=0;i<6;i++) {
        if(a[i]<0 || a[i]>255)return false;
        v[i]=(unsigned)a[i];
    }
    return true;
}
static void bart_v15_save_six(const char *path,const unsigned *v)
{
    FILE *f=fopen(path,"w");
    if(!f)return;
    fprintf(f,"%u %u %u %u %u %u\n",v[0],v[1],v[2],v[3],v[4],v[5]);
    fclose(f);
}
static void bart_v15_tune_poll()
{
    static unsigned long next_check=0;
    if(next_check && !CheckTimer(next_check))return;
    next_check=GetTimer(600);
    FILE *f=fopen("/tmp/bart-v15-tune.req","r");
    if(!f)return;
    char req[128]={};
    bool have=!!fgets(req,sizeof(req),f);
    fclose(f);
    unlink("/tmp/bart-v15-tune.req");
    FILE *out=fopen("/tmp/bart-v15-tune.last","w");
    if(!out)return;
    if(!have) {
        fprintf(out,"ERROR empty request\n");
        fclose(out);return;
    }

    unsigned desired[6]={},old[6]={},observed[6]={};
    if(!bart_v15_all_read(old)) {
        fprintf(out,"ERROR BART_V15 FPGA does not support verified E9F0..E9F5 reads; settings unchanged\n");
        fclose(out);return;
    }
    if(!strncmp(req,"restore",7)) {
        FILE *pf=fopen("/tmp/bart-v15-previous","r");
        char line[128]={};
        bool ok=pf && fgets(line,sizeof(line),pf);
        if(pf)fclose(pf);
        if(!ok || !bart_v15_parse_six(line,desired)) {
            fprintf(out,"ERROR no valid previous v15 timing profile to restore\n");
            fclose(out);return;
        }
    } else if(!strncmp(req,"zero",4)) {
        // all 0: upstream bridge timing
    } else if(!strncmp(req,"baseline",8)) {
        desired[0]=1; // prior chip-wait 1/0 behaviour
    } else if(!bart_v15_parse_six(req,desired)) {
        fprintf(out,"ERROR BART_V15 expects 6 integers 0..255 (CHIP CIA READ WRITE CUSTOM BLIT), baseline, zero, or restore\n");
        fclose(out);return;
    }

    // All old registers are captured from the LIVE FPGA first.
    // Verify every write using an independent read-only SPI request.
    for(int i=0;i<6;i++) {
        bart_v15_write_slot(i,desired[i]);
        unsigned got=999;
        if(!bart_v15_read_slot(i,&got) || got!=desired[i]) {
            for(int j=0;j<6;j++) bart_v15_write_slot(j,old[j]);
            fprintf(out,"ERROR BART_V15 register %d readback mismatch: requested=%u got=%u; attempted to restore former live values\n",
                    i,desired[i],got);
            fclose(out);return;
        }
    }
    if(!bart_v15_all_read(observed)) {
        for(int j=0;j<6;j++)bart_v15_write_slot(j,old[j]);
        fprintf(out,"ERROR BART_V15 final full readback failed; attempted rollback\n");
        fclose(out);return;
    }
    for(int i=0;i<6;i++)if(observed[i]!=desired[i]) {
        for(int j=0;j<6;j++)bart_v15_write_slot(j,old[j]);
        fprintf(out,"ERROR BART_V15 final settings differ; attempted rollback\n");
        fclose(out);return;
    }
    bart_v15_save_six("/tmp/bart-v15-previous",old);
    bart_v15_save_six("/tmp/bart-v15-current",observed);
    fprintf(out,
      "OK BART_V15 CHIP=%u CIA=%u READ=%u WRITE=%u CUSTOM=%u BLIT=%u VERIFIED=6/6; F12 Reset Amiga before testing\n",
      observed[0],observed[1],observed[2],observed[3],observed[4],observed[5]);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{",
           "new v15 on-demand handler")
    s=once(s,"\t\tbart_v11_wait_poll();\n\t\tbart_v14_tune_poll();",
           "\t\tbart_v15_tune_poll(); // all v15 controls are 8-bit",
           "replace old 2-bit pollers")
    path.write_text(s)
    print("Bart v15 Main E900..E905 8-bit writes, E9F0..E9F5 live readback.")
    print("On-demand profile save/restore and baseline/zero; original floppy Main retained.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_main_tuning_v15.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
