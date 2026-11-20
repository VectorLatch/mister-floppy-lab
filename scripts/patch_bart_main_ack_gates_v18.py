#!/usr/bin/env python3
"""v18 Main: read independent 32-bit CPU /DTACK and write strobe gate counters."""
from pathlib import Path
import subprocess
import sys
PINNED="d2757b2c420b1336f51c0ff641f3bad4d3c2c3c2"
def once(s,a,b,label):
    n=s.count(a)
    if n!=1:raise ValueError(f"{label}: wanted one anchor, found {n}")
    return s.replace(a,b,1)
def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise ValueError("Wrong pinned Main "+sha)
    path=root/"user_io.cpp"
    s=path.read_text()
    if "bart_v17_spi_word" not in s or "bart_v17_diagnostics_poll();" not in s:
        raise ValueError("Requires v17 Main patches")
    block=r'''
// V18 read-only gate counters. Share v17 EC00/EC01 atomic snapshot/clear.
// ED7F returns D718, ED20..ED2F 8x32-bit frozen counters.
// The v17 EC2E seq proves the cross-version snapshot completed.
static bool bart_v18_read_gates(uint32_t values[8],uint16_t *seq)
{
    if(bart_v17_spi_word(0xEC7F)!=0xC717 ||
       bart_v17_spi_word(0xED7F)!=0xD718) return false;
    uint16_t oldseq=bart_v17_spi_word(0xEC2E);
    if(bart_v17_spi_word(0xEC00)!=0xC700) return false;
    uint16_t newseq=bart_v17_spi_word(0xEC2E);
    if((uint16_t)(newseq-oldseq)!=1) return false;
    for(int i=0;i<8;i++){
        uint16_t lo=bart_v17_spi_word((uint16_t)(0xED20+i*2));
        uint16_t hi=bart_v17_spi_word((uint16_t)(0xED21+i*2));
        values[i]=(uint32_t)lo|((uint32_t)hi<<16);
    }
    if(bart_v17_spi_word(0xEC2E)!=newseq) return false;
    *seq=newseq;
    return true;
}
static void bart_v18_gates_poll()
{
    static unsigned long next_check=0;
    if(next_check && !CheckTimer(next_check))return;
    next_check=GetTimer(500);
    FILE *f=fopen("/tmp/bart-v18-gates.req","r");
    if(!f)return;
    char req[64]={};
    bool have=!!fgets(req,sizeof(req),f);
    fclose(f);
    unlink("/tmp/bart-v18-gates.req");
    FILE *out=fopen("/tmp/bart-v18-gates.last","w");
    if(!out)return;
    if(!have){
        fprintf(out,"ERROR BART_V18 empty request\n");
        fclose(out);return;
    }
    bool clear=!strncmp(req,"clear",5);
    if(!clear && strncmp(req,"snapshot",8) && strncmp(req,"status",6)){
        fprintf(out,"ERROR BART_V18 expects clear, snapshot or status\n");
        fclose(out);return;
    }
    if(bart_v17_spi_word(0xEC7F)!=0xC717 ||
       bart_v17_spi_word(0xED7F)!=0xD718){
        fprintf(out,"ERROR BART_V18 wrong FPGA signature; nothing changed\n");
        fclose(out);return;
    }
    if(clear && bart_v17_spi_word(0xEC01)!=0xC701){
        fprintf(out,"ERROR BART_V18 clear not acknowledged; do not trust counters\n");
        fclose(out);return;
    }
    uint32_t c[8]={};
    uint16_t seq=0;
    if(!bart_v18_read_gates(c,&seq)){
        fprintf(out,"ERROR BART_V18 snapshot/sequence invalid; do not trust counters\n");
        fclose(out);return;
    }
    fprintf(out,
      "OK BART_V18 SEQ=%u PREACK_BUSY=%u POSTACK_BUSY=%u PREACK_RAW_LOW=%u PREACK_RAW_HIGH=%u PREACK_WRITES=%u WRITE_STROBES=%u BUSY_STROBES=%u ACTIVE_WAITS=%u\n",
      (unsigned)seq,(unsigned)c[0],(unsigned)c[1],(unsigned)c[2],
      (unsigned)c[3],(unsigned)c[4],(unsigned)c[5],(unsigned)c[6],
      (unsigned)c[7]);
    fclose(out);
}
'''
    s=once(s,"void user_io_poll()\n{",block+"\nvoid user_io_poll()\n{","v18 diagnostic handler")
    s=once(s,
       "\t\tbart_v17_diagnostics_poll(); // independent 32-bit counters",
       "\t\tbart_v17_diagnostics_poll(); // independent 32-bit counters\n"
       "\t\tbart_v18_gates_poll(); // before/after DTACK and actual writes",
       "poll v18")
    path.write_text(s)
    print("v18 Main: verified ED7F/EC7F signature, shared atomic EC00 snapshot with eight extra counters.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_main_ack_gates_v18.py <pinned Main root>")
    apply(Path(sys.argv[1]).resolve())
