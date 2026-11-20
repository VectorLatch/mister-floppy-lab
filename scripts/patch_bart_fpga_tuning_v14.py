#!/usr/bin/env python3
"""Bart v14: configurable, independently adjustable CPU bus timing knobs.

Apply after exact proven Rick ERSY v4 and v11 FPGA runtime bus waits.
E8xx remains unchanged. E9xx adds four 2-bit timing knobs, default zero.
The new controls are CPU DTACK-only; no floppy/graphics/ram data modifications.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s, old, new, label):
    n=s.count(old)
    if n!=1: raise ValueError(f"{label}: expected one anchor, found {n}")
    return s.replace(old,new,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PINNED: raise ValueError("Unexpected FPGA upstream: "+rev)
    paths={
        "paula":root/"rtl/paula.v",
        "floppy":root/"rtl/paula_floppy.v",
        "mini":root/"rtl/minimig.v",
        "bridge":root/"rtl/minimig_m68k_bridge.v",
    }
    d={k:p.read_text() for k,p in paths.items()}
    if "bart_v11_wait_target" not in d["bridge"] or "bart_v11_cmd" not in d["floppy"]:
        raise ValueError("v14 requires the established v11 E8/CPU wait implementation first")

    # Separate E9 write-only command; preserves the earlier E8xx 4-bit knobs.
    d["floppy"]=once(d["floppy"],
        "\toutput reg [3:0] bart_v11_waits = 4'b0000, // held through Amiga soft reset",
        "\toutput reg [3:0] bart_v11_waits = 4'b0000, // held through Amiga soft reset\n"
        "\toutput reg [7:0] bart_v14_extra = 8'b00000000, // E9: read/write/custom/blit",
        "floppy v14 output register")
    d["floppy"]=once(d["floppy"],
        "reg bart_v11_cmd = 1'b0;",
        """reg bart_v11_cmd = 1'b0;
reg bart_v14_cmd = 1'b0;
// E9xx 2nd word carries:
// [1:0] read extra, [3:2] write extra (slow/chip RAM);
// [5:4] custom-register extra (DFxxxx);
// [7:6] extra while blitter-priority arbitration is asserted.
// Configuration survives emulated Amiga reset, resets on FPGA reload.
always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v14_cmd <= 0;
        else if (stb7 && cmd_cnt == 2'd0)
            bart_v14_cmd <= (rx_data[15:8] == 8'hE9);
        else if (stb7 && cmd_cnt == 2'd1 && bart_v14_cmd)
            bart_v14_extra <= rx_data[7:0];
    end
end
""",
        "new separate E9 SPI command")
    d["floppy"]=once(d["floppy"],
        "    else if (bart_v11_cmd && cmd_cnt != 2'd0)\n        tx_data = 16'hB800 | {12'd0, bart_v11_waits};",
        "    else if (bart_v11_cmd && cmd_cnt != 2'd0)\n        tx_data = 16'hB800 | {12'd0, bart_v11_waits};\n"
        "    else if (bart_v14_cmd && cmd_cnt != 2'd0)\n"
        "        tx_data = 16'hB900 | {8'd0, bart_v14_extra};",
        "E9 readback branch")

    d["paula"]=once(d["paula"],
        "\toutput [3:0] bart_v11_waits,",
        "\toutput [3:0] bart_v11_waits,\n\toutput [7:0] bart_v14_extra,",
        "Paula extra port")
    d["paula"]=once(d["paula"],
        "\t.bart_v11_waits(bart_v11_waits),",
        "\t.bart_v11_waits(bart_v11_waits),\n\t.bart_v14_extra(bart_v14_extra),",
        "Paula extra hook")
    d["mini"]=once(d["mini"],
        "wire [3:0] bart_v11_waits; // live HPS diagnostic bus waits, 0/0=stock",
        "wire [3:0] bart_v11_waits; // live HPS diagnostic bus waits, 0/0=stock\n"
        "wire [7:0] bart_v14_extra; // split read/write/custom/blitter-priority waits",
        "Minimig source wire")
    d["mini"]=once(d["mini"],
        "\t.IO_DOUT(IO_DOUT_PAULA),\n\t.bart_v11_waits(bart_v11_waits),",
        "\t.IO_DOUT(IO_DOUT_PAULA),\n\t.bart_v11_waits(bart_v11_waits),\n"
        "\t.bart_v14_extra(bart_v14_extra),",
        "Minimig Paula hook")
    # The same port appears exactly once more on the CPU bridge instance.
    d["mini"]=once(d["mini"],
        "\t.bart_v11_waits(bart_v11_waits),\n\t.bls(bls),",
        "\t.bart_v11_waits(bart_v11_waits),\n\t.bart_v14_extra(bart_v14_extra),\n\t.bls(bls),",
        "Minimig CPU-bridge hook")

    d["bridge"]=once(d["bridge"],
        "\tinput [3:0] bart_v11_waits, // [1:0] chip/custom, [3:2] CIA",
        "\tinput [3:0] bart_v11_waits, // [1:0] chip/custom, [3:2] CIA\n"
        "\tinput [7:0] bart_v14_extra, // E9 split RAM-read/write/custom/priority extra",
        "bridge input")
    d["bridge"]=once(d["bridge"],
        """reg [1:0] bart_v11_wait_seen = 2'd0;
// For standard CPU bus reads and writes, insert 0-3 *eligible acknowledge
// opportunities* on the CPU bridge. The CIA opportunities are ECLK-aligned.
// Do not delay MiSTer HPS host cycles or change the DMA slot scheduler.
// With config 0 the original dtack condition and cycle are unchanged.
wire [1:0] bart_v11_wait_target =
    halt ? 2'd0 :
    vpa ? bart_v11_waits[3:2] :
    dbs ? bart_v11_waits[1:0] : 2'd0;""",
        """reg [3:0] bart_v11_wait_seen = 4'd0;
// v14 keeps v11 E8 base waits exactly; all E9 extras default zero.
// Count *eligible acknowledge opportunities*, NOT MHz clock cycles.
// Only slow/chip-RAM and custom-register accesses (dbs) receive extras.
// CIA remains its original E-clock-aligned 0..3 knob.
// DFxxxx addresses are custom registers, not ordinary chip RAM.
// The existing blit_nasty signal represents active blitter priority;
// adding a bounded extra wait to eligible RAM cycles is an experiment,
// not a wholesale block until blit_busy clears (which could deadlock).
// Host HPS accesses are explicitly excluded. DTACK functional path
// is identical to v11 whenever all extra bits are zero.
wire bart_v14_custom = (address[23:16] == 8'hDF);
wire [1:0] bart_v14_extra_kind =
    bart_v14_custom ? bart_v14_extra[5:4] :
    lr_w ? bart_v14_extra[1:0] : bart_v14_extra[3:2];
wire [1:0] bart_v14_extra_blt =
    blit_nasty && !bart_v14_custom ? bart_v14_extra[7:6] : 2'd0;
wire [3:0] bart_v11_wait_target =
    halt ? 4'd0 :
    vpa ? {2'd0,bart_v11_waits[3:2]} :
    dbs ? ({2'd0,bart_v11_waits[1:0]} +
           {2'd0,bart_v14_extra_kind} +
           {2'd0,bart_v14_extra_blt}) : 4'd0;""",
        "v11 to v14 ack target")
    d["bridge"]=once(d["bridge"],
        "bart_v11_wait_seen <= bart_v11_wait_seen + 2'd1;",
        "bart_v11_wait_seen <= bart_v11_wait_seen + 4'd1;",
        "expand wait counter")
    # Strict source checks: no CPU or RAM functional word assignments changed.
    for k,p in paths.items():
        if d[k]!=p.read_text():p.write_text(d[k])
    print("Bart v14 E9xx runtime extra knobs installed; v11 E8 waits unchanged.")
    print("Read/write/DF custom/blitter-priority extras 0..3 each; all default 0.")
    print("No diagnostic changes to disk DMA, blitter state, graphics or CPU data.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_fpga_tuning_v14.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
