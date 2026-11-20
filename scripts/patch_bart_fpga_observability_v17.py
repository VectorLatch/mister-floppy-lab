#!/usr/bin/env python3
"""V17 nonintrusive 32-bit blitter/CPU activity counters on pinned v16 FPGA.

SPI EC7F identifies v17 (C717); EC00 latches atomically, EC01 clears;
EC20..EC2D read 14 frozen 16-bit words; EC2E is snapshot sequence.
All counts are INDEPENDENT of v16 mode and of the v16 8-bit hit counter.
Counts are per CPU address-strobe transaction, not per sustained bus cycle.
"""
from pathlib import Path
import subprocess
import sys

PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,a,b,label):
    n=s.count(a)
    if n!=1: raise ValueError(f"{label}: expected one anchor, found {n}")
    return s.replace(a,b,1)

def apply(root):
    actual=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if actual!=PINNED: raise ValueError("Wrong upstream FPGA: "+actual)
    paths={k:root/path for k,path in {
       "mini":"rtl/minimig.v","paula":"rtl/paula.v",
       "floppy":"rtl/paula_floppy.v","bridge":"rtl/minimig_m68k_bridge.v"
    }.items()}
    d={k:p.read_text() for k,p in paths.items()}
    if "bart_v16_active_wait" not in d["bridge"] or "bart_v16_cmd" not in d["floppy"]:
        raise ValueError("Requires the pinned v11/v14/v15/v16 FPGA patch sequence")

    # SPI control resides in Paula-floppy, with read-only snapshot data from
    # the CPU bridge. All new control traffic is ECxx, not E9xx or EBxx.
    flopports="""\toutput reg bart_v17_snapshot_pulse = 1'b0,
\toutput reg bart_v17_clear_pulse = 1'b0,
\toutput reg [3:0] bart_v17_word_sel = 4'd0,
\tinput [15:0] bart_v17_word,"""
    otherports="""\toutput bart_v17_snapshot_pulse,
\toutput bart_v17_clear_pulse,
\toutput [3:0] bart_v17_word_sel,
\tinput [15:0] bart_v17_word,"""
    hook="""\t.bart_v17_snapshot_pulse(bart_v17_snapshot_pulse),
\t.bart_v17_clear_pulse(bart_v17_clear_pulse),
\t.bart_v17_word_sel(bart_v17_word_sel),
\t.bart_v17_word(bart_v17_word),"""
    d["floppy"]=once(d["floppy"],
        "\tinput [7:0] bart_v16_expired,",
        "\tinput [7:0] bart_v16_expired,\n"+flopports,
        "v17 floppy ports")
    d["paula"]=once(d["paula"],
        "\tinput [7:0] bart_v16_expired,",
        "\tinput [7:0] bart_v16_expired,\n"+otherports,
        "v17 Paula ports")
    d["paula"]=once(d["paula"],
        "\t.bart_v16_expired(bart_v16_expired),",
        "\t.bart_v16_expired(bart_v16_expired),\n"+hook,
        "v17 floppy source wiring")

    spi=r'''// Bart v17 independent diagnostic bus: ECxx (not v15 E9 or v16 EB).
// EC7F -> C717 signature; EC00 SNAPSHOT; EC01 CLEAR.
// EC20..EC2D -> frozen 16-bit halves of 7 x 32-bit counters.
// EC2E -> atomic snapshot sequence, incremented by every EC00.
// Command actions occur at cmd_cnt==1. Pulses are one clk7_en period.
reg bart_v17_cmd = 1'b0;
reg bart_v17_is_read = 1'b0;
reg bart_v17_is_version = 1'b0;
reg bart_v17_is_snapshot = 1'b0;
reg bart_v17_is_clear = 1'b0;
always @(posedge clk) begin
    if (clk7_en) begin
        bart_v17_snapshot_pulse <= 1'b0;
        bart_v17_clear_pulse <= 1'b0;
        if (!IO_ENA) bart_v17_cmd <= 1'b0;
        else if (stb7 && cmd_cnt == 2'd0) begin
            bart_v17_is_read <= rx_data[15:4] == 12'hEC2 &&
                                 rx_data[3:0] <= 4'd14;
            bart_v17_is_version <= rx_data == 16'hEC7F;
            bart_v17_is_snapshot <= rx_data == 16'hEC00;
            bart_v17_is_clear <= rx_data == 16'hEC01;
            bart_v17_cmd <= (rx_data[15:4] == 12'hEC2 &&
                             rx_data[3:0] <= 4'd14) ||
                             rx_data == 16'hEC7F ||
                             rx_data == 16'hEC00 ||
                             rx_data == 16'hEC01;
            bart_v17_word_sel <= rx_data[3:0];
        end
        else if (stb7 && cmd_cnt == 2'd1 && bart_v17_cmd) begin
            if (bart_v17_is_snapshot) bart_v17_snapshot_pulse <= 1'b1;
            if (bart_v17_is_clear) bart_v17_clear_pulse <= 1'b1;
        end
    end
end
'''
    d["floppy"]=once(d["floppy"],
        "reg bart_v16_cmd = 1'b0;",
        spi+"\nreg bart_v16_cmd = 1'b0;",
        "v17 command recognition")
    d["floppy"]=once(d["floppy"],
        """    else if (bart_v16_cmd && cmd_cnt != 2'd0)
        tx_data = (16'hB600 + ({13'd0,bart_v16_slot} << 8)) | {8'd0,bart_v16_reply};""",
        """    else if (bart_v16_cmd && cmd_cnt != 2'd0)
        tx_data = (16'hB600 + ({13'd0,bart_v16_slot} << 8)) | {8'd0,bart_v16_reply};
    else if (bart_v17_cmd && cmd_cnt != 2'd0)
        tx_data = bart_v17_is_version ? 16'hC717 :
                  bart_v17_is_read ? bart_v17_word :
                  bart_v17_is_snapshot ? 16'hC700 :
                  bart_v17_is_clear ? 16'hC701 : 16'hC7EE;""",
        "v17 SPI mux")

    wires="""wire bart_v17_snapshot_pulse;
wire bart_v17_clear_pulse;
wire [3:0] bart_v17_word_sel;
wire [15:0] bart_v17_word;"""
    d["mini"]=once(d["mini"],
        "wire [7:0] bart_v16_expired;",
        "wire [7:0] bart_v16_expired;\n"+wires,
        "v17 minimig wires")
    # Both Paula and CPU bridge have same v16 stats hook line; share v17 hooks.
    if d["mini"].count("\t.bart_v16_expired(bart_v16_expired),")!=2:
        raise ValueError("Expected exactly 2 v16 completed hooks in minimig")
    d["mini"]=d["mini"].replace(
        "\t.bart_v16_expired(bart_v16_expired),",
        "\t.bart_v16_expired(bart_v16_expired),\n"+hook)

    bridgeports="""\tinput bart_v17_snapshot_pulse,
\tinput bart_v17_clear_pulse,
\tinput [3:0] bart_v17_word_sel,
\toutput [15:0] bart_v17_word,"""
    d["bridge"]=once(d["bridge"],
        "\toutput [7:0] bart_v16_expired,",
        "\toutput [7:0] bart_v16_expired,\n"+bridgeports,
        "v17 bridge ports")

    bridge=r'''// Bart v17 independent, observational diagnostic counters.
// All counters 32-bit and explicitly cleared via HPS EC01; they do not
// reset on F12 Amiga reset. Snapshots are atomically latched by HPS EC00.
//
// These are intentionally independent of v16's 'HITS' signal:
// 0 blit starts       : Agnus blit_busy rising edge
// 1 CPU blit writes   : one attempted CPU write per /AS transaction,
//                       any address $DF0040..$DF0074
// 2 CPU busy writes   : such CPU write with real Agnus busy overlapping,
//                       whether or not v16 MODE enables a wait
// 3 CPU RAM busy      : CPU chip/slow access while blitter busy
// 4 wait candidates   : v16 exact wait candidate, counted ONCE per /AS
// 5 CPU bus cycles    : all CPU /AS transactions (sanity control)
// 6 blitter busy ticks: 7MHz samples with real Agnus busy (sanity control)
//
// Sample request when l_as is low and re-arm on l_as high. Even a held
// bus cycle increments once. HPS host cycles are explicitly excluded.
// Counters are not fed back into the DMA scheduler, DTACK or memory paths.
reg [31:0] bart_v17_count_starts = 32'd0;
reg [31:0] bart_v17_count_writes = 32'd0;
reg [31:0] bart_v17_count_busy_writes = 32'd0;
reg [31:0] bart_v17_count_ram_busy = 32'd0;
reg [31:0] bart_v17_count_candidates = 32'd0;
reg [31:0] bart_v17_count_cycles = 32'd0;
reg [31:0] bart_v17_count_busy_ticks = 32'd0;
reg [223:0] bart_v17_frozen = 224'd0;
reg [15:0] bart_v17_seq = 16'd0;

reg bart_v17_prev_busy = 1'b0;
reg bart_v17_seen_cycle = 1'b0;
reg bart_v17_seen_write = 1'b0;
reg bart_v17_seen_busy_write = 1'b0;
reg bart_v17_seen_ram_busy = 1'b0;
reg bart_v17_seen_candidate = 1'b0;
wire bart_v17_bus_active = !halt && !l_as;
wire bart_v17_blit_write = bart_v17_bus_active && blt_wr;
wire bart_v17_ram_access = bart_v17_bus_active && dbs &&
                            address[23:16] != 8'hDF && !vpa;
assign bart_v17_word = bart_v17_word_sel == 4'd14 ? bart_v17_seq :
                          bart_v17_frozen[{bart_v17_word_sel,4'b0000} +: 16];

always @(posedge clk) begin
    if (clk7_en) begin
        if (bart_v17_clear_pulse) begin
            bart_v17_count_starts <= 32'd0;
            bart_v17_count_writes <= 32'd0;
            bart_v17_count_busy_writes <= 32'd0;
            bart_v17_count_ram_busy <= 32'd0;
            bart_v17_count_candidates <= 32'd0;
            bart_v17_count_cycles <= 32'd0;
            bart_v17_count_busy_ticks <= 32'd0;
            bart_v17_frozen <= 224'd0;
            bart_v17_seq <= 16'd0;
            bart_v17_prev_busy <= bart_v16_blit_busy_cpu;
            bart_v17_seen_cycle <= 1'b0;
            bart_v17_seen_write <= 1'b0;
            bart_v17_seen_busy_write <= 1'b0;
            bart_v17_seen_ram_busy <= 1'b0;
            bart_v17_seen_candidate <= 1'b0;
        end else begin
            bart_v17_prev_busy <= bart_v16_blit_busy_cpu;
            if (bart_v16_blit_busy_cpu) begin
                bart_v17_count_busy_ticks <= bart_v17_count_busy_ticks + 32'd1;
                if (!bart_v17_prev_busy)
                    bart_v17_count_starts <= bart_v17_count_starts + 32'd1;
            end
            if (!bart_v17_bus_active) begin
                bart_v17_seen_cycle <= 1'b0;
                bart_v17_seen_write <= 1'b0;
                bart_v17_seen_busy_write <= 1'b0;
                bart_v17_seen_ram_busy <= 1'b0;
                bart_v17_seen_candidate <= 1'b0;
            end else begin
                if (!bart_v17_seen_cycle) begin
                    bart_v17_count_cycles <= bart_v17_count_cycles + 32'd1;
                    bart_v17_seen_cycle <= 1'b1;
                end
                if (bart_v17_blit_write && !bart_v17_seen_write) begin
                    bart_v17_count_writes <= bart_v17_count_writes + 32'd1;
                    bart_v17_seen_write <= 1'b1;
                end
                if (bart_v17_blit_write && bart_v16_blit_busy_cpu &&
                    !bart_v17_seen_busy_write) begin
                    bart_v17_count_busy_writes <= bart_v17_count_busy_writes + 32'd1;
                    bart_v17_seen_busy_write <= 1'b1;
                end
                if (bart_v17_ram_access && bart_v16_blit_busy_cpu &&
                    !bart_v17_seen_ram_busy) begin
                    bart_v17_count_ram_busy <= bart_v17_count_ram_busy + 32'd1;
                    bart_v17_seen_ram_busy <= 1'b1;
                end
                if (bart_v16_candidate && !bart_v17_seen_candidate) begin
                    bart_v17_count_candidates <= bart_v17_count_candidates + 32'd1;
                    bart_v17_seen_candidate <= 1'b1;
                end
            end
            if (bart_v17_snapshot_pulse) begin
                bart_v17_frozen <= {
                    bart_v17_count_busy_ticks,
                    bart_v17_count_cycles,
                    bart_v17_count_candidates,
                    bart_v17_count_ram_busy,
                    bart_v17_count_busy_writes,
                    bart_v17_count_writes,
                    bart_v17_count_starts
                };
                bart_v17_seq <= bart_v17_seq + 16'd1;
            end
        end
    end
end
'''
    d["bridge"]=once(d["bridge"],
        "assign bart_v16_expired = bart_v16_timeout_count;",
        "assign bart_v16_expired = bart_v16_timeout_count;\n"+bridge,
        "v17 counter logic")
    for k,p in paths.items():
        if d[k]!=p.read_text():p.write_text(d[k])
    print("Bart v17: seven 32-bit activity counters, atomic snapshot, explicit reset.")
    print("EC7F version; EC00 snapshot; EC01 clear; EC20..EC2D data; EC2E sequence.")
    print("Read-only counters; no DMA scheduling, CPU DTACK, floppy, or blitter logic modifications.")

if __name__=="__main__":
    if len(sys.argv)!=2: raise SystemExit("Usage: patch_bart_fpga_observability_v17.py <pinned fpga root>")
    apply(Path(sys.argv[1]).resolve())
