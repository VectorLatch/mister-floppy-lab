#!/usr/bin/env python3
"""Bart v18: eight 32-bit read-only gate and actual write-strobe counters.

Apply after v17 to exact pinned Minimig source. EC00 snapshots BOTH v17
and v18 simultaneously and EC01 clears BOTH. ED7F identifies v18 D718;
ED20..ED2F accesses 16 frozen 16-bit words.
"""
from pathlib import Path
import subprocess
import sys
PINNED="7d5d3c2f685af4ce3eb361c22893fccd153f2d87"

def once(s,old,new,label):
    count=s.count(old)
    if count!=1:raise ValueError(f"{label}: wanted one anchor, found {count}")
    return s.replace(old,new,1)

def apply(root):
    rev=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True).strip()
    if rev!=PINNED:raise ValueError("Wrong pinned FPGA source "+rev)
    paths={k:root/v for k,v in {
      "mini":"rtl/minimig.v",
      "paula":"rtl/paula.v",
      "floppy":"rtl/paula_floppy.v",
      "bridge":"rtl/minimig_m68k_bridge.v"
    }.items()}
    d={k:p.read_text() for k,p in paths.items()}
    if "bart_v17_count_busy_writes" not in d["bridge"] or "bart_v17_cmd" not in d["floppy"]:
        raise ValueError("Apply v17 on pinned v16 patches before v18")

    # No new standalone snapshot/clear; piggyback the validated EC00/EC01
    # snapshot edges, so v17 and v18 can be compared at same moment.
    d["floppy"]=once(d["floppy"],
      "\tinput [15:0] bart_v17_word,",
      "\tinput [15:0] bart_v17_word,\n\tinput [15:0] bart_v18_word,",
      "floppy v18 input")
    spi=r'''// v18 ED bus-gate diagnostics (read only).
// ED7F -> D718; ED20..ED2F -> 8 x 32-bit frozen gate counters.
// Uses v17 EC00 snapshot/EC01 clear so both data sets are coherent.
reg bart_v18_cmd = 1'b0;
reg bart_v18_is_version = 1'b0;
always @(posedge clk) begin
    if (clk7_en) begin
        if (!IO_ENA) bart_v18_cmd <= 1'b0;
        else if (stb7 && cmd_cnt == 2'd0) begin
            bart_v18_cmd <= ((rx_data[15:4] == 12'hED2) ||
                             (rx_data == 16'hED7F));
            bart_v18_is_version <= rx_data == 16'hED7F;
        end
    end
end
'''
    d["floppy"]=once(d["floppy"],
      "reg bart_v17_cmd = 1'b0;",
      spi+"\nreg bart_v17_cmd = 1'b0;",
      "new v18 ED read commands")
    d["floppy"]=once(d["floppy"],
      """    else if (bart_v17_cmd && cmd_cnt != 2'd0)
        tx_data = bart_v17_is_version ? 16'hC717 :
                  bart_v17_is_read ? bart_v17_word :
                  bart_v17_is_snapshot ? 16'hC700 :
                  bart_v17_is_clear ? 16'hC701 : 16'hC7EE;""",
      """    else if (bart_v17_cmd && cmd_cnt != 2'd0)
        tx_data = bart_v17_is_version ? 16'hC717 :
                  bart_v17_is_read ? bart_v17_word :
                  bart_v17_is_snapshot ? 16'hC700 :
                  bart_v17_is_clear ? 16'hC701 : 16'hC7EE;
    else if (bart_v18_cmd && cmd_cnt != 2'd0)
        tx_data = bart_v18_is_version ? 16'hD718 : bart_v18_word;""",
      "ED readback mux")
    d["paula"]=once(d["paula"],
      "\tinput [15:0] bart_v17_word,",
      "\tinput [15:0] bart_v17_word,\n\tinput [15:0] bart_v18_word,",
      "paula v18 port")
    d["paula"]=once(d["paula"],
      "\t.bart_v17_word(bart_v17_word),",
      "\t.bart_v17_word(bart_v17_word),\n\t.bart_v18_word(bart_v18_word),",
      "paula FPGA v18 hookup")
    d["mini"]=once(d["mini"],
      "wire [15:0] bart_v17_word;",
      "wire [15:0] bart_v17_word;\nwire [15:0] bart_v18_word;",
      "minimig v18 shared word")
    if d["mini"].count("\t.bart_v17_word(bart_v17_word),")!=2:
        raise ValueError("Expected Paula and CPU bridge v17 words")
    d["mini"]=d["mini"].replace(
      "\t.bart_v17_word(bart_v17_word),",
      "\t.bart_v17_word(bart_v17_word),\n\t.bart_v18_word(bart_v18_word),")

    d["bridge"]=once(d["bridge"],
      "\toutput [15:0] bart_v17_word,",
      "\toutput [15:0] bart_v17_word,\n\toutput [15:0] bart_v18_word,",
      "bridge v18 port")

    counters=r'''// v18: 8 independent 32-bit gates and actual CPU write strobe counts.
// Sampled at clk7_en; 1 increment per CPU /AS transaction (not each tick).
// 0 PRE_ACK_BUSY: CPU blitter-register address cycle while Agnus busy,
//                 before /DTACK asserted (_ta_n=1).
// 1 POST_ACK_BUSY: same after /DTACK asserted (_ta_n=0).
// 2 PRE_ACK_RAW_LOW: PRE_ACK_BUSY while raw /AS still asserted.
// 3 PRE_ACK_RAW_HIGH: PRE_ACK_BUSY while raw /AS already deasserted.
// 4 PRE_ACK_WRITES: CPU blitter-register writes before /DTACK,
//                   independent of blitter busy.
// 5 WRITE_STROBES: actual bridge write strobes (hwr/lwr) to blitter regs.
// 6 BUSY_WRITE_STROBES: such actual write strobes with blitter busy.
// 7 ACTIVE_WAITS: actual v16 active wait state observed at least once.
// Counters do not interfere with /DTACK or blitter scheduling.
reg [31:0] bart_v18_c0 = 32'd0;
reg [31:0] bart_v18_c1 = 32'd0;
reg [31:0] bart_v18_c2 = 32'd0;
reg [31:0] bart_v18_c3 = 32'd0;
reg [31:0] bart_v18_c4 = 32'd0;
reg [31:0] bart_v18_c5 = 32'd0;
reg [31:0] bart_v18_c6 = 32'd0;
reg [31:0] bart_v18_c7 = 32'd0;
reg [255:0] bart_v18_frozen = 256'd0;
reg [7:0] bart_v18_seen = 8'd0;

wire bart_v18_pre = bart_v17_blit_write && _ta_n;
wire bart_v18_busy = bart_v17_blit_write && bart_v16_blit_busy_cpu;
wire bart_v18_commit = !halt && blt_wr && (hwr || lwr);
wire [7:0] bart_v18_events = {
    bart_v16_active_wait,
    (bart_v18_commit && bart_v16_blit_busy_cpu),
    bart_v18_commit,
    bart_v18_pre,
    (bart_v18_busy && _ta_n && _as_and_cs),
    (bart_v18_busy && _ta_n && !_as_and_cs),
    (bart_v18_busy && !_ta_n),
    (bart_v18_busy && _ta_n)
};
assign bart_v18_word = bart_v18_frozen[{bart_v17_word_sel,4'b0000} +: 16];

always @(posedge clk) begin
    if (clk7_en) begin
        if (bart_v17_clear_pulse) begin
            bart_v18_c0 <= 32'd0;
            bart_v18_c1 <= 32'd0;
            bart_v18_c2 <= 32'd0;
            bart_v18_c3 <= 32'd0;
            bart_v18_c4 <= 32'd0;
            bart_v18_c5 <= 32'd0;
            bart_v18_c6 <= 32'd0;
            bart_v18_c7 <= 32'd0;
            bart_v18_seen <= 8'd0;
            bart_v18_frozen <= 256'd0;
        end else begin
            if (!bart_v17_bus_active) bart_v18_seen <= 8'd0;
            else begin
                if (bart_v18_events[0] && !bart_v18_seen[0]) begin
                    bart_v18_c0 <= bart_v18_c0 + 32'd1;
                    bart_v18_seen[0] <= 1'b1;
                end
                if (bart_v18_events[1] && !bart_v18_seen[1]) begin
                    bart_v18_c1 <= bart_v18_c1 + 32'd1;
                    bart_v18_seen[1] <= 1'b1;
                end
                if (bart_v18_events[2] && !bart_v18_seen[2]) begin
                    bart_v18_c2 <= bart_v18_c2 + 32'd1;
                    bart_v18_seen[2] <= 1'b1;
                end
                if (bart_v18_events[3] && !bart_v18_seen[3]) begin
                    bart_v18_c3 <= bart_v18_c3 + 32'd1;
                    bart_v18_seen[3] <= 1'b1;
                end
                if (bart_v18_events[4] && !bart_v18_seen[4]) begin
                    bart_v18_c4 <= bart_v18_c4 + 32'd1;
                    bart_v18_seen[4] <= 1'b1;
                end
                if (bart_v18_events[5] && !bart_v18_seen[5]) begin
                    bart_v18_c5 <= bart_v18_c5 + 32'd1;
                    bart_v18_seen[5] <= 1'b1;
                end
                if (bart_v18_events[6] && !bart_v18_seen[6]) begin
                    bart_v18_c6 <= bart_v18_c6 + 32'd1;
                    bart_v18_seen[6] <= 1'b1;
                end
                if (bart_v18_events[7] && !bart_v18_seen[7]) begin
                    bart_v18_c7 <= bart_v18_c7 + 32'd1;
                    bart_v18_seen[7] <= 1'b1;
                end
            end
            if (bart_v17_snapshot_pulse) begin
                bart_v18_frozen <= {
                    bart_v18_c7,bart_v18_c6,bart_v18_c5,bart_v18_c4,
                    bart_v18_c3,bart_v18_c2,bart_v18_c1,bart_v18_c0
                };
            end
        end
    end
end
'''
    d["bridge"]=once(d["bridge"],
        "assign bart_v17_word = bart_v17_word_sel == 4'd14 ? bart_v17_seq :\n                          bart_v17_frozen[{bart_v17_word_sel,4'b0000} +: 16];",
        "assign bart_v17_word = bart_v17_word_sel == 4'd14 ? bart_v17_seq :\n                          bart_v17_frozen[{bart_v17_word_sel,4'b0000} +: 16];\n"+counters,
        "insert v18 independent counters")
    for k,p in paths.items():
        if d[k]!=p.read_text(): p.write_text(d[k])
    print("Bart v18: eight 32-bit CPU ACK gate counters and real blitter register write strobes.")
    print("v17 EC00 atomic snapshot/EC01 clear shared; v18 ED7F identification and ED20..ED2F read-only.")
    print("No changes to v16 stall or physical floppy data path.")

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("Usage: patch_bart_fpga_ack_gates_v18.py <pinned FPGA root>")
    apply(Path(sys.argv[1]).resolve())
