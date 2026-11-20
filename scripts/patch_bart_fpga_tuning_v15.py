#!/usr/bin/env python3
"""Bart v15 six 8-bit CPU bus timing knobs, built upon v11+v14 patches.

Eight bits each: CHIP, CIA, READ_EXTRA, WRITE_EXTRA, CUSTOM_EXTRA, BLIT_EXTRA.
E900..E905 select the register; second SPI word writes low eight bits.
A900..AE00 | value are distinct per-control readback prefixes.
No CPU, RAM, blitter, or floppy functional datapath changes: only CPU
DTACK timing. All six controls reset on full FPGA reload, not F12 reset.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,a,b,where):
    count=s.count(a)
    if count!=1:raise ValueError(f"{where}: expected one anchor, got {count}")
    return s.replace(a,b,1)

def between(s,start,end,replacement,label):
    a=s.find(start)
    if a<0 or s.find(start,a+1)>=0:raise ValueError(label+": start not unique")
    b=s.find(end,a)
    if b<0:raise ValueError(label+": end missing")
    return s[:a]+replacement+s[b:]

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise ValueError("Wrong pinned FPGA: "+sha)
    paths={
        "paula":root/"rtl/paula.v",
        "floppy":root/"rtl/paula_floppy.v",
        "mini":root/"rtl/minimig.v",
        "bridge":root/"rtl/minimig_m68k_bridge.v"
    }
    d={k:p.read_text() for k,p in paths.items()}
    if "bart_v14_extra" not in d["floppy"] or "bart_v14_extra_kind" not in d["bridge"]:
        raise ValueError("Apply original v11 waits, then v14 tuning, before this patch")

    d["floppy"]=once(d["floppy"],
        "\toutput reg [7:0] bart_v14_extra = 8'b00000000, // E9: read/write/custom/blit",
        "\toutput reg [47:0] bart_v15_waits = 48'd0, // six independent 8-bit E9 controls",
        "FPGA six settings register")

    start="reg bart_v14_cmd = 1'b0;"
    end="""always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v11_cmd"""
    spi=r'''// Six individually addressed E9 register writes:
 // E900 CHIP (base), E901 CIA, E902 RAM_READ_EXTRA,
 // E903 RAM_WRITE_EXTRA, E904 DF_CUSTOM_EXTRA, E905 BLITTER_EXTRA.
 // Ack responses: A900..AE00 OR the latched 8-bit value.
 // This prevents the v14 Main from silently talking to v15 FPGA.
reg bart_v15_cmd = 1'b0;
reg [2:0] bart_v15_sel = 3'd0;
wire [7:0] bart_v15_readback = bart_v15_waits[bart_v15_sel*8 +: 8];
always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v15_cmd <= 1'b0;
        else if (stb7 && cmd_cnt == 2'd0) begin
            bart_v15_cmd <= (rx_data[15:3] == 13'h1D20) && (rx_data[2:0] <= 3'd5);
            bart_v15_sel <= rx_data[2:0];
        end
        else if (stb7 && cmd_cnt == 2'd1 && bart_v15_cmd)
            bart_v15_waits[bart_v15_sel*8 +: 8] <= rx_data[7:0];
    end
end
'''
    # 16'hE900 shifted right by three gives 13'h1D20.
    d["floppy"]=between(d["floppy"],start,end,spi+"\n","E9 decoder")
    d["floppy"]=once(d["floppy"],
        """    else if (bart_v14_cmd && cmd_cnt != 2'd0)
        tx_data = 16'hB900 | {8'd0, bart_v14_extra};""",
        """    else if (bart_v15_cmd && cmd_cnt != 2'd0)
        tx_data = 16'hA900 | ({13'd0,bart_v15_sel} << 8) | {8'd0,bart_v15_readback};""",
        "8-bit per-register echoed readback")
    d["paula"]=once(d["paula"],
        "\toutput [7:0] bart_v14_extra,",
        "\toutput [47:0] bart_v15_waits,",
        "Paula six config output")
    d["paula"]=once(d["paula"],
        "\t.bart_v14_extra(bart_v14_extra),",
        "\t.bart_v15_waits(bart_v15_waits),",
        "Paula source hook")
    d["mini"]=once(d["mini"],
        "wire [7:0] bart_v14_extra; // split read/write/custom/blitter-priority waits",
        "wire [47:0] bart_v15_waits; // chip, CIA, read, write, custom, blit as bytes",
        "Minimig six config bus")
    d["mini"]=d["mini"].replace("\t.bart_v14_extra(bart_v14_extra),",
                               "\t.bart_v15_waits(bart_v15_waits),")
    if d["mini"].count("\t.bart_v15_waits(bart_v15_waits),")!=2:
        raise ValueError("Expected exactly Paula and bridge v15 config hooks")
    d["bridge"]=once(d["bridge"],
        "\tinput [7:0] bart_v14_extra, // E9 split RAM-read/write/custom/priority extra",
        "\tinput [47:0] bart_v15_waits, // six 0..255 timing controls: E900..E905",
        "bridge config input")
    d["bridge"]=once(d["bridge"],
        "reg [3:0] bart_v11_wait_seen = 4'd0;",
        "reg [9:0] bart_v11_wait_seen = 10'd0;",
        "wider wait counter")
    start="// v14 keeps v11 E8 base waits exactly; all E9 extras default zero."
    end="wire bart_v11_can_ack ="
    new=r'''// v15 replaces E8/E9 2-bit settings with six independent E9 bytes.
// The old v11 register is retained for source compatibility but must NOT
// affect the new 0..255 controls (all zero = original bridge timing).
// Count eligible CPU DTACK opportunities, not sysclk cycles. max=765.
// Custom DFxxxx is a distinct setting; CIA is ECLK-qualified.
// BLIT_EXTRA applies to chip/slow-RAM while blitter-priority arbitration
// is asserted; it does not make CPU wait for "blitter busy" globally.
// Existing HPS host transactions are excluded via halt. This design does
// NOT alter Agnus blitter sequencing, DMA grant, or CPU read data.
wire bart_v15_custom = (address[23:16] == 8'hDF);
wire [7:0] bart_v15_kind =
    bart_v15_custom ? bart_v15_waits[39:32] :
    lr_w ? bart_v15_waits[23:16] : bart_v15_waits[31:24];
wire [7:0] bart_v15_priority =
    (blit_nasty && !bart_v15_custom) ? bart_v15_waits[47:40] : 8'd0;
wire [9:0] bart_v11_wait_target =
    halt ? 10'd0 :
    vpa ? {2'd0,bart_v15_waits[15:8]} :
    dbs ? ({2'd0,bart_v15_waits[7:0]} +
           {2'd0,bart_v15_kind} +
           {2'd0,bart_v15_priority}) : 10'd0;
'''
    d["bridge"]=between(d["bridge"],start,end,new, "v15 wait sum")
    d["bridge"]=once(d["bridge"],
        "bart_v11_wait_seen <= bart_v11_wait_seen + 4'd1;",
        "bart_v11_wait_seen <= bart_v11_wait_seen + 10'd1;",
        "wider opportunity count increment")
    for k,p in paths.items():
        if d[k]!=p.read_text():p.write_text(d[k])
    print("Bart v15 E900..E905: CHIP CIA READ WRITE CUSTOM BLIT, each 0..255.")
    print("Responses A900..AE00 | latched byte; full 10-bit combined wait count.")
    print("Rick ERSY and floppy retained; no blitter/DMA/CPU data modifications.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_fpga_tuning_v15.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
