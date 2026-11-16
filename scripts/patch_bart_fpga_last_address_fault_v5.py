#!/usr/bin/env python3
"""Bart fx68k last-two address error recorder v5 (after v1,v2,v3,v4).

V4's FIRST two observations are not the terminal events: its on-device
log counted 1143 address-error condition episodes before the CPU halted.
Re-use V4's 15 read slots (45..59) as a two-entry sliding history of
the MOST RECENT (penultimate, latest) address-error condition episodes.

The fault context includes the 32-bit internal full address (including
A0), internal PC, Ird, PSW, and microaddress; the top four bits of each
16-bit UADDR slot [13:10] now carry the sequencer's GROUP0 flags *at
that event*, distinguishing a new fault while the CPU is handling an
earlier address exception. Nothing drives functional CPU control.
"""
from pathlib import Path
import subprocess
import sys

PINNED = "7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, label):
    n=s.count(old)
    if n != 1:
        raise ValueError(f"{label}: expected one match, found {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(
        ["git","-C",str(root),"rev-parse","HEAD"],text=True
    ).strip()
    if sha != PINNED:
        raise ValueError(f"Wrong upstream FPGA commit {sha}")
    fx=root/"rtl/fx68k/fx68k.sv"
    fl=root/"rtl/paula_floppy.v"
    s=fx.read_bytes().decode("utf-8")
    fp=fl.read_text()
    if "oDbgFault1Address" not in s or "bart_seq_grp0" not in s:
        raise ValueError("Apply pinned v1, v2, v3 and v4 patches first")
    start_marker="// Read-only first-two address error recorder."
    end_marker="\n\tassign oDbgMicroAddr = microAddr;"
    start=s.find(start_marker)
    end=s.find(end_marker,start)
    if start<0 or end<0 or s.find(start_marker,start+1)>=0:
        raise ValueError("Cannot uniquely locate v4 internal recorder block")
    # This deliberately leaves the existing fx68k busAddrErr generator,
    # error latches, microcode and exception sequencer untouched.
    # Move latest -> previous at each *new* qualified episode, then
    # write the current snapshot into latest. Nonblocking assignments
    # preserve the old latest sample while doing the shift.
    block="""// Bart V5: last TWO odd word/long access-condition episodes.
// The probe's event qualification exactly matches V4 and matches
// the core's rAddrErr set condition (busAddrErr && addrOe at phi1).
// Such condition episodes are NOT necessarily one-to-one with
// architecturally dispatched address-error exceptions.
reg bart_addrerr_prev;
wire bart_addrerr_active = busAddrErr && addrOe;
always @(posedge clk) begin
    if (Clks.extReset) begin
        bart_addrerr_prev <= 1'b0;
        oDbgFaultCount <= 16'd0;
        oDbgFault1Address <= 32'd0;
        oDbgFault1Pc <= 32'd0;
        oDbgFault1Psw <= 16'd0;
        oDbgFault1Ird <= 16'd0;
        oDbgFault1Uaddr <= 16'd0;
        oDbgFault2Address <= 32'd0;
        oDbgFault2Pc <= 32'd0;
        oDbgFault2Psw <= 16'd0;
        oDbgFault2Ird <= 16'd0;
        oDbgFault2Uaddr <= 16'd0;
    end else if (Clks.enPhi1) begin
        bart_addrerr_prev <= bart_addrerr_active;
        if (bart_addrerr_active && !bart_addrerr_prev) begin
            if (oDbgFaultCount != 16'hFFFF)
                oDbgFaultCount <= oDbgFaultCount + 16'd1;
            // History slot 1 is the previous event; slot 2 the latest.
            oDbgFault1Address <= oDbgFault2Address;
            oDbgFault1Pc <= oDbgFault2Pc;
            oDbgFault1Psw <= oDbgFault2Psw;
            oDbgFault1Ird <= oDbgFault2Ird;
            oDbgFault1Uaddr <= oDbgFault2Uaddr;
            oDbgFault2Address <= bart_fault_live_address;
            oDbgFault2Pc <= bart_fault_live_pc;
            oDbgFault2Psw <= psw;
            oDbgFault2Ird <= Ird;
            // Pack group-0 exception state with microaddress.
            // [13:10]: {inGrp0Exc,rExcAdrErr,rExcBusErr,rExcRst}.
            // [9:0]: internal microAddr (0x001 is HALT microcode).
            oDbgFault2Uaddr <= {2'b00,bart_seq_grp0,microAddr};
        end
    end
end
"""
    s=s[:start]+block+s[end:]
    fp=once(fp,"6'd0: bart_diag_word = 16'hB4A9;",
        "6'd0: bart_diag_word = 16'hB4AA;","FPGA v5 signature")
    fp=once(fp,"6'd1: bart_diag_word = 16'd4;",
        "6'd1: bart_diag_word = 16'd5;","FPGA v5 protocol")
    # Existing 60 register map and its mux/counters are unchanged.
    fx.write_bytes(s.encode("utf-8"))
    fl.write_text(fp)
    print("V5: replaced first-two recorder with last-two sliding history.")
    print("V5: packed group0 flags into uaddr slots 52/59.")
    print("V5: 60-word SPI protocol B4AA version 5; no functional core changes.")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: patch_bart_fpga_last_address_fault_v5.py <FPGA source>")
    apply(Path(sys.argv[1]).resolve())
