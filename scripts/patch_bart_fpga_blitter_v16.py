#!/usr/bin/env python3
"""Bart v16 CPU blitter-completion interlock, on top of pinned v15 HDL.

This does not patch Bart's software and does not emulate the 30 exact
WHDLoad insertion points. It stalls CPU writes to selected blitter
registers until Agnus blit_busy drops; host, Copper and floppy remain
untouched. While stalled it relinquishes the normal CPU 'bls' pressure
so blitter DMA can finish; bounded independent 7MHz-cycle watchdog
avoids permanent waits if the blitter is jammed or DMA disabled.
"""
from pathlib import Path
import subprocess
import sys
PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,why):
    n=s.count(old)
    if n!=1:raise ValueError(f"{why}: wanted exactly one anchor, got {n}")
    return s.replace(old,new,1)

def apply(root):
    sha=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if sha!=PINNED:raise ValueError("wrong pinned FPGA: "+sha)
    paths={
      "agnus":root/"rtl/agnus.v",
      "mini":root/"rtl/minimig.v",
      "bridge":root/"rtl/minimig_m68k_bridge.v",
      "paula":root/"rtl/paula.v",
      "floppy":root/"rtl/paula_floppy.v",
    }
    d={k:p.read_text() for k,p in paths.items()}
    if "bart_v15_waits" not in d["bridge"] or "bart_v15_cmd" not in d["floppy"]:
        raise ValueError("Apply v11, v14, v15 FPGA patches first.")

    # Agnus reports the actual busy bit, the same signal in DMACONR.
    d["agnus"]=once(d["agnus"],
        "\toutput        blit_nasty,",
        "\toutput        blit_nasty,\n\toutput        bart_v16_blit_busy_cpu, // actual DMACONR busy state",
        "expose busy port")
    d["agnus"]=once(d["agnus"],
        "wire        blit_busy;       //blitter busy status",
        "wire        blit_busy;       //blitter busy status\n"
        "assign bart_v16_blit_busy_cpu = blit_busy;",
        "actual blitter busy status")

    ports="""\toutput reg [7:0] bart_v16_mode = 8'd0, // off / start only / all blitter writes
\toutput reg [7:0] bart_v16_timeout = 8'd64, // 1 unit = 256 * 7MHz clock opportunities
\tinput [7:0] bart_v16_hits,
\tinput [7:0] bart_v16_done,
\tinput [7:0] bart_v16_expired,"""
    d["floppy"]=once(d["floppy"],
        "\toutput reg [47:0] bart_v15_waits = 48'd0, // six independent 8-bit E9 controls",
        "\toutput reg [47:0] bart_v15_waits = 48'd0, // six independent 8-bit E9 controls\n"+ports,
        "floppy V16 ports")

    # EB00 MODE, EB01 TIMEOUT, EBF0..EBF4 read only mode/time/stats.
    block=r'''// Bart v16: interlock configuration, separate from all v15 E9 registers.
 // Mode 0=off, 1=BLTSIZE/BLTSIZH starts only,
 // 2=any CPU write to DF0040..DF0074 blitter register group.
 // Timeout: number of 256-tick groups at clk7n_en; minimum one group.
 // Counter bytes wrap at 255; only diagnostic, never affect timing.
reg bart_v16_cmd = 1'b0;
reg bart_v16_write = 1'b0;
reg [2:0] bart_v16_slot = 3'd0;
wire [7:0] bart_v16_reply =
    bart_v16_slot == 3'd0 ? bart_v16_mode :
    bart_v16_slot == 3'd1 ? bart_v16_timeout :
    bart_v16_slot == 3'd2 ? bart_v16_hits :
    bart_v16_slot == 3'd3 ? bart_v16_done : bart_v16_expired;
always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v16_cmd <= 1'b0;
        else if (stb7 && cmd_cnt == 2'd0) begin
            bart_v16_cmd <=
                ((rx_data[15:1] == 15'h7580) ||
                 (rx_data[15:4] == 12'hEBF)) &&
                ((rx_data[15:1] == 15'h7580 && rx_data[0] <= 1'd1) ||
                 (rx_data[15:4] == 12'hEBF && rx_data[3:0] <= 4'd4));
            bart_v16_write <= rx_data[15:1] == 15'h7580;
            bart_v16_slot <= rx_data[2:0];
        end
        else if (stb7 && cmd_cnt == 2'd1 && bart_v16_cmd && bart_v16_write) begin
            if(bart_v16_slot == 3'd0) bart_v16_mode <= rx_data[7:0];
            else if(bart_v16_slot == 3'd1) bart_v16_timeout <= rx_data[7:0];
        end
    end
end
'''
    d["floppy"]=once(d["floppy"],
        "reg bart_v15_cmd = 1'b0;",
        block+"\nreg bart_v15_cmd = 1'b0;",
        "V16 EB command control")
    d["floppy"]=once(d["floppy"],
        """    else if (bart_v15_cmd && cmd_cnt != 2'd0)
        tx_data = (16'hA900 + ({13'd0,bart_v15_sel} << 8)) | {8'd0,bart_v15_readback};""",
        """    else if (bart_v15_cmd && cmd_cnt != 2'd0)
        tx_data = (16'hA900 + ({13'd0,bart_v15_sel} << 8)) | {8'd0,bart_v15_readback};
    else if (bart_v16_cmd && cmd_cnt != 2'd0)
        tx_data = (16'hB600 + ({13'd0,bart_v16_slot} << 8)) | {8'd0,bart_v16_reply};""",
        "V16 SPI verified responses")

    pports="""\toutput [7:0] bart_v16_mode,
\toutput [7:0] bart_v16_timeout,
\tinput [7:0] bart_v16_hits,
\tinput [7:0] bart_v16_done,
\tinput [7:0] bart_v16_expired,"""
    hooks="""\t.bart_v16_mode(bart_v16_mode),
\t.bart_v16_timeout(bart_v16_timeout),
\t.bart_v16_hits(bart_v16_hits),
\t.bart_v16_done(bart_v16_done),
\t.bart_v16_expired(bart_v16_expired),"""
    d["paula"]=once(d["paula"],
        "\toutput [47:0] bart_v15_waits,",
        "\toutput [47:0] bart_v15_waits,\n"+pports,
        "Paula V16 port")
    d["paula"]=once(d["paula"],
        "\t.bart_v15_waits(bart_v15_waits),",
        "\t.bart_v15_waits(bart_v15_waits),\n"+hooks,
        "Paula V16 hookup")

    wiredefs="""wire [7:0] bart_v16_mode;
wire [7:0] bart_v16_timeout;
wire [7:0] bart_v16_hits;
wire [7:0] bart_v16_done;
wire [7:0] bart_v16_expired;"""
    d["mini"]=once(d["mini"],
        "wire [47:0] bart_v15_waits; // chip, CIA, read, write, custom, blit as bytes",
        "wire [47:0] bart_v15_waits; // chip, CIA, read, write, custom, blit as bytes\n"+wiredefs,
        "minimig V16 shared wires")
    d["mini"]=once(d["mini"],
        "wire        blit_nasty;",
        "wire        blit_nasty;\nwire bart_v16_blit_busy_cpu;",
        "minimig Agnus busy wire")
    d["mini"]=once(d["mini"],
        "\t.int3(int3),\n\t.blit_nasty(blit_nasty),",
        "\t.int3(int3),\n\t.blit_nasty(blit_nasty),\n\t.bart_v16_blit_busy_cpu(bart_v16_blit_busy_cpu),",
        "minimig Agnus busy connection")
    # Paired v15 settings hook occurs twice: Paula and CPU bridge.
    if d["mini"].count("\t.bart_v15_waits(bart_v15_waits),")!=2:
        raise ValueError("expected two distinct v15 settings ports in minimig")
    d["mini"]=d["mini"].replace(
        "\t.bart_v15_waits(bart_v15_waits),",
        "\t.bart_v15_waits(bart_v15_waits),\n"+hooks)
    d["mini"]=once(d["mini"],
        "\t.blit_nasty(blit_nasty),\n\t.memory_config(memory_config[3:0]),",
        "\t.blit_nasty(blit_nasty),\n"
        "\t.bart_v16_blit_busy_cpu(bart_v16_blit_busy_cpu),\n"
        "\t.memory_config(memory_config[3:0]),",
        "CPU bridge busy connection")

    d["bridge"]=once(d["bridge"],
        "\tinput [47:0] bart_v15_waits, // six 0..255 timing controls: E900..E905",
        "\tinput [47:0] bart_v15_waits, // six 0..255 timing controls: E900..E905\n"
        "\tinput [7:0] bart_v16_mode,\n"
        "\tinput [7:0] bart_v16_timeout,\n"
        "\tinput bart_v16_blit_busy_cpu,\n"
        "\toutput [7:0] bart_v16_hits,\n"
        "\toutput [7:0] bart_v16_done,\n"
        "\toutput [7:0] bart_v16_expired,",
        "bridge V16 ports")

    interlock=r'''// v16 blitter-completion interlock.
// Unlike v15 BLIT_EXTRA (only fixed CPU DTACK opportunities while nasty),
// v16 uses the actual blitter busy state and releases as soon as it is idle.
// Two independently selectable CPU WRITE address scopes:
//   mode 1: BLTSIZE $DF0058 or ECS BLTSIZH $DF005E (start of new blit)
//   mode 2: existing 'blt_wr' decode ($DF0040..$DF0074; all blitter regs)
// No Copper, HPS host, CPU reads, floppy DMA, or other register writes delayed.
// While waiting, release the CPU's normal BLS priority so blitter DMA CAN
// complete. Critical: otherwise CPU waiting on busy can STARVE blitter.
// A 16-bit, 7MHz-cycle-based watchdog caps the stall (1..255 x 256 ticks).
// In frozen/misconfigured DMA conditions, expire and allow old CPU write.
// All values and statistics reset on full FPGA reload, not F12 soft reset.
wire bart_v16_blit_start_reg =
    (address[23:16] == 8'hDF) &&
    ((address[8:1] == 8'h2C) || (address[8:1] == 8'h2F));
wire bart_v16_scope =
    (bart_v16_mode == 8'd1 && bart_v16_blit_start_reg) ||
    (bart_v16_mode == 8'd2 && blt_wr);
wire bart_v16_candidate =
    !halt && !_as_and_cs && !l_as && !lr_w && _ta_n &&
    bart_v16_scope && bart_v16_blit_busy_cpu;
reg [15:0] bart_v16_busy_ticks = 16'd0;
wire [15:0] bart_v16_limit_ticks =
    {bart_v16_timeout == 8'd0 ? 8'd1 : bart_v16_timeout,8'd0};
wire bart_v16_timed_out =
    bart_v16_busy_ticks >= bart_v16_limit_ticks;
wire bart_v16_active_wait =
    bart_v16_candidate && !bart_v16_timed_out;

reg bart_v16_tracking = 1'b0;
reg [7:0] bart_v16_hit_count = 8'd0;
reg [7:0] bart_v16_complete_count = 8'd0;
reg [7:0] bart_v16_timeout_count = 8'd0;
assign bart_v16_hits = bart_v16_hit_count;
assign bart_v16_done = bart_v16_complete_count;
assign bart_v16_expired = bart_v16_timeout_count;
always @(posedge clk) begin
    if (clk7n_en) begin
        if (!bart_v16_candidate) bart_v16_busy_ticks <= 16'd0;
        else if (!bart_v16_timed_out)
            bart_v16_busy_ticks <= bart_v16_busy_ticks + 16'd1;

        if (!bart_v16_tracking && bart_v16_active_wait) begin
            bart_v16_tracking <= 1'b1;
            bart_v16_hit_count <= bart_v16_hit_count + 8'd1;
        end else if (bart_v16_tracking && !bart_v16_blit_busy_cpu) begin
            bart_v16_tracking <= 1'b0;
            bart_v16_complete_count <= bart_v16_complete_count + 8'd1;
        end else if (bart_v16_tracking && bart_v16_timed_out) begin
            bart_v16_tracking <= 1'b0;
            bart_v16_timeout_count <= bart_v16_timeout_count + 8'd1;
        end else if (!bart_v16_candidate)
            bart_v16_tracking <= 1'b0;
    end
end
'''
    d["bridge"]=once(d["bridge"],
        "wire bart_v11_can_ack =",
        interlock+"\nwire bart_v11_can_ack =",
        "insert actual blitter-busy interlock")
    d["bridge"]=once(d["bridge"],
        "if (bart_v11_can_ack) begin",
        "if (bart_v11_can_ack && !bart_v16_active_wait) begin",
        "gate CPU DTACK before write reaches custom chip")
    d["bridge"]=once(d["bridge"],
        "assign bls = dbs & ~l_as & l_dtack;",
        "assign bls = dbs & ~l_as & l_dtack & !bart_v16_active_wait;",
        "allow blitter DMA while waiting")
    # Note all combined v15 CPU wait counters stay unchanged.
    for name,path in paths.items():
        if d[name]!=path.read_text():path.write_text(d[name])
    print("Bart v16: real Agnus blit busy interlock, mode 0/1/2, timeout 1..255*256 7MHz ticks.")
    print("BLS suppression during interlock avoids CPU-vs-blitter starvation.")
    print("Readback EB F0..F4: mode, timeout, hits, busy-cleared, watchdog expirations.")
    print("Old v15 timing knobs, physical floppy and Rick ERSY v4 fix preserved.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: patch_bart_fpga_blitter_v16.py <pinned fpga root>")
    apply(Path(sys.argv[1]).resolve())
